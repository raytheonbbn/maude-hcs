"""Executable checks for IRC failover integrated with main's socket batching."""
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
IRC = ROOT / "maude_hcs/lib/irc"
pytestmark = pytest.mark.skipif(not shutil.which("maude"), reason="Maude CLI required")


def run_maude(tmp_path, source):
    executable = Path(shutil.which("maude")).resolve()
    scenario = tmp_path / "scenario.maude"
    scenario.write_text(source)
    env = dict(os.environ)
    env.setdefault("MAUDE_LIB", str(executable.parent))
    result = subprocess.run(
        [str(executable), "-no-banner", "-no-advise", str(scenario)],
        cwd=ROOT, env=env, text=True, capture_output=True, timeout=30,
    )
    trace = result.stdout + result.stderr
    (tmp_path / "maude.log").write_text(trace)
    assert result.returncode == 0, trace
    assert not re.search(r"Warning:|Error:|Advisory:", trace), trace
    flat = re.sub(r"\s+", " ", trace)
    assert "result Config:" in flat, flat
    assert not re.search(r"result Config:.*\brun\(", flat), flat
    return flat


@pytest.mark.parametrize("link_up", [True, False])
def test_batched_peer_messages_do_not_stall(tmp_path, link_up):
    trace = run_maude(tmp_path, f'''sload "{IRC / 'cp4-topology.maude'}"
set print attribute on .
rew run({{0.0 | nil}} rCtr(10) serverTreeConfig
 [0.0, (to ifs12 from ifs12 : SetLinkState({str(link_up).lower()})), 0]
 [0.1, (to ifs12 from ircSAd1 :
   SrvPrivMsg(makeIrcChannelName("#chat"), makeIrcUserName(ircCAd1), "first", ircSAd1) ;;
   SrvPrivMsg(makeIrcChannelName("#chat"), makeIrcUserName(ircCAd1), "second", ircSAd1)), 0], 1.0) .
quit
''')
    if link_up:
        assert 'received SrvPrivMsg' in trace
        assert 'Link DOWN - dropped outgoing' not in trace
    else:
        assert 'Link DOWN - dropped outgoing' in trace
        assert 'received SrvPrivMsg' not in trace


def test_legacy_client_ping_keeps_batched_output(tmp_path):
    trace = run_maude(tmp_path, f'''sload "{IRC / 'cp4-topology.maude'}"
set print attribute on .
rew run({{0.0 | nil}} rCtr(10) ircMonitor
 mkIrcClient-v2(ircCAd1, ifc1p, "legacy")
 mkIrcServer(ircSAd1)
 mkIrcByteSeqIface(ifc1p, ircCAd1, ifs1c1)
 mkIrcByteSeqIface(ifs1c1, ircSAd1, ifc1p)
 [0.1, (to ircCAd1 from ifc1p : Ping(makeIrcUserName(ircCAd1), ircSAd1)), 0], 1.0) .
quit
''')
    assert 'IRC ircCAd1 flushing output messages' in trace
    assert 'IrcIface ifc1p transforms Pong' in trace


def test_connected_tree_failover_baseline(tmp_path):
    trace = run_maude(
        tmp_path, f'sload "{IRC / "test-irc-failover-baseline.maude"}"\n'
    )
    assert 'starting FAILOVER' in trace
    assert 'send completed' in trace


@pytest.mark.parametrize("confirm_second", [True, False])
def test_rejoin_uses_channel_count_and_timeout_floor(tmp_path, confirm_second):
    # Three 5 ms RTT samples yield the committed 50 ms per-channel floor.
    # Two channels therefore have a shared 100 ms rejoin deadline.
    second = (
        '[10.075, (to ircCAd1 from ifc1p : SessionDelivery(2, '
        'JoinChannel(makeIrcChannelName("#general"), ircCAd1))), 0]'
        if confirm_second else ""
    )
    trace = run_maude(tmp_path, f'''sload "{IRC / 'cp4-topology.maude'}"
mod REBASE-REJOIN-TEST is
 inc IRC-CP4-TOPOLOGY .
 op calibrating : Actor -> Actor .
 eq calibrating(< A:Address : IrcClient | AS:AttributeSet,
      connState: disconnected, pingEpoch: 0, rttCount: 0,
      rttSum: 0.0, lastPingSentAt: 0.0, sendQueue: emptySendQueue >)
  = < A:Address : IrcClient | AS:AttributeSet,
      connState: rtt-baseline, pingEpoch: 2, rttCount: 2,
      rttSum: 0.01, lastPingSentAt: 9.995,
      sendQueue: (queued(PrivMsgReq(makeIrcChannelName("#chat"),
                         makeIrcUserName(ircCAd1), "first")) ++
                 queued(PrivMsgReq(makeIrcChannelName("#chat"),
                         makeIrcUserName(ircCAd1), "second"))) > .
 op acceptingSocket : -> Actor .
 eq acceptingSocket = < ifc1p : IrcSessionIface |
   ircAddress: ircCAd1, epAddress: ifs1c1, linkUp: false,
   clientSide: true, wireDelay: 0.03,
   sessionEpoch: 2, sessionLive: true, socketBroken: false > .
endm
set print attribute on .
rew run({{0.0 | nil}} rCtr(10)
 calibrating(mkIrcClient-cp4(ircCAd1, (ifc1p ; ifc1b), "alice1",
   makeIrcChannelName("#chat") :: makeIrcChannelName("#general"), 120.0, 120.0))
 acceptingSocket
 mkIrcSessionIface(ifc1b, ircCAd1, ifs2c1, true, ircCAd1)
 [0.0, (to ifc1b from ircCAd1 : SetLinkState(false)), 0]
 [10.0, (to ircCAd1 from ifc1p : SessionDelivery(2,
   RttPong(makeIrcUserName(ircCAd1), ircSAd1, 2, 3))), 0]
 [10.01, (to ircCAd1 from ifc1p : SessionDelivery(2,
   JoinChannel(makeIrcChannelName("#chat"), ircCAd1))), 0]
 {second}, 10.2) .
quit
''')
    calibrated = re.search(r'pongTimeout=([-+\deE.]+), joining channels', trace)
    assert calibrated and float(calibrated[1]) == pytest.approx(0.05)
    if confirm_second:
        assert 'starting FAILOVER' not in trace
        completions = re.findall(
            r'\(([-+\deE.]+)\) IRC Client ircCAd1 send completed.*?"(first|second)"', trace
        )
        assert [payload for _, payload in completions] == ['first', 'second']
        assert all(float(time) == pytest.approx(10.075) for time, _ in completions)
    else:
        failover = re.search(
            r'\(([-+\deE.]+)\) IRC Client ircCAd1 starting FAILOVER', trace
        )
        assert failover and float(failover[1]) == pytest.approx(10.1)
        assert 'send completed' not in trace
