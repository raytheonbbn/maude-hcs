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
    trace = run_maude(tmp_path, f'''sload "{IRC / 'cp4_test_topology.maude'}"
set print attribute on .
rew run({{0.0 | nil}} rCtr(10) serverTreeConfig
 [0.0, (to ifs12 from ifs12 : SetLinkState({str(link_up).lower()})), 0]
 [0.1, (to ifs12 from ircSAd1 :
   PrivMsgReq(makeIrcChannelName("#chat"), makeIrcUserName(ircCAd1), "first", ircSAd1) ;;
   PrivMsgReq(makeIrcChannelName("#chat"), makeIrcUserName(ircCAd1), "second", ircSAd1)), 0], 1.0) .
quit
''')
    if link_up:
        assert 'received PrivMsgReq' in trace
        assert 'Link DOWN - dropped outgoing' not in trace
        final = trace.split('result Config:', 1)[1]
        assert len(re.findall(r'messageTimestamp\([^,]+, ircSAd1, ifs21,', final)) == 2
        assert len(re.findall(r'messageTimestamp\([^,]+, ifs12, ircSAd2,', final)) == 2
        assert 'ircLinkOutput(' not in final
        assert 'ircLinkInput(' not in final
    else:
        assert 'Link DOWN - dropped outgoing' in trace
        assert 'received PrivMsgReq' not in trace


def test_legacy_client_ping_keeps_batched_output(tmp_path):
    trace = run_maude(tmp_path, f'''sload "{IRC / 'cp4_test_topology.maude'}"
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
    trace = run_maude(tmp_path, f'''sload "{IRC / 'cp4_test_topology.maude'}"
mod REBASE-REJOIN-TEST is
 inc IRC-CP4-TEST-TOPOLOGY .
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
 op acceptingSocket : -> IrcSessionTable .
 eq acceptingSocket = sessionEndpoint(ifc1p, (
   localIrcAddress: ircCAd1, peerEndpointAddress: ifs1c1, isLinkUp: false,
   clientSide: true, wireDelay: 0.03,
   sessionEpoch: 2, sessionLive: true, socketBroken: false)) .
endm
set print attribute on .
rew run({{0.0 | nil}} rCtr(10)
 withIrcSessions(
   calibrating(mkIrcClient-cp4(ircCAd1, (ifc1p ; ifc1b), "alice1",
     makeIrcChannelName("#chat") :: makeIrcChannelName("#general"), 120.0, 120.0)),
   acceptingSocket mkIrcSessionEndpoint(ifc1b, ircCAd1, ifs2c1, true, ircCAd1))
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


def session_scenario(records, events, end=1.0, server=False):
    """Observe transport deliveries on existing actors with minimal IRC state."""
    actor_type = "IrcServer" if server else "IrcClient"
    owners = '\n'.join(
        f'withIrcSessions(< {owner} : {actor_type} | testSink: true >, {table})'
        for owner, table in records.items()
    )
    return f'''sload "{IRC / 'cp4_test_topology.maude'}"
mod SHARED-SESSION-TEST is
 inc IRC-CP4-TEST-TOPOLOGY .
 ops local1 local2 endpoint1 endpoint2 peer1 peer2 : -> Address .
 op TestSink : -> ActorType .
 op captured:_ : Content -> Attribute [ctor] .
 op testSink:_ : Bool -> Attribute [ctor] .
 op payload : String -> IrcMsg .
 eq payload(text:String) = PrivMsgRes(makeIrcChannelName("#chat"),
   makeIrcUserName(local1), text:String) .
 op liveEndpoint : Address Address Address Bool -> IrcSessionTable .
 eq liveEndpoint(endpoint:Address, local:Address, peer:Address, client:Bool)
  = sessionEndpoint(endpoint:Address, (
      localIrcAddress: local:Address, peerEndpointAddress: peer:Address,
      isLinkUp: true, clientSide: client:Bool,
      sessionUser: (if client:Bool then local:Address else peer:Address fi),
      wireDelay: 0.001, sessionEpoch: 2, sessionLive: true,
      socketBroken: false, idleSince: 0.0, pingSent: -1.0,
      registrationUntil: 0.0)) .
 rl [capture-transport-delivery]:
   < sink:Address : sinkType:ActorType | attrs:AttributeSet, testSink: true >
   {{time:Float, (to sink:Address from source:Address : content:Content)}}
  =>
   < sink:Address : sinkType:ActorType | attrs:AttributeSet, testSink: true,
     captured: content:Content > .
endm
set print attribute on .
rew run({{0.0 | nil}} rCtr(10)
 {owners}
 < peer1 : TestSink | testSink: true > < peer2 : TestSink | testSink: true >
 {events}, {end}) .
quit
'''


def test_owned_sessions_keep_partition_state_per_endpoint(tmp_path):
    trace = run_maude(tmp_path, session_scenario(
        {'local1': 'liveEndpoint(endpoint1, local1, peer1, true) '
                   'liveEndpoint(endpoint2, local1, peer2, true)'},
        '''[0.0, (to endpoint1 from local1 : SetLinkState(false)), 0]
 [0.1, (to endpoint1 from local1 : ClientWrite(2, payload("partitioned"))), 0]
 [0.1, (to endpoint2 from local1 : ClientWrite(2, payload("reachable"))), 0]''',
    ))
    final = trace.split('result Config:', 1)[1]
    # A partition does not fail a local write or affect a different endpoint.
    assert final.count('captured: WriteAccepted(2,') == 2
    assert 'captured: WriteRejected' not in final
    assert final.count('captured: SessionWire(2,') == 1
    assert re.search(r'< peer1 : TestSink \| testSink: true >', final)
    assert re.search(r'< peer2 : TestSink \|.*?captured: SessionWire\(2,.*?"reachable"', final)


def test_owned_sessions_reject_stale_epoch_and_report_current_reset(tmp_path):
    trace = run_maude(tmp_path, session_scenario(
        {'local1': 'liveEndpoint(endpoint1, local1, peer1, true)'},
        '''[0.1, (to endpoint1 from peer1 : SessionWire(1, payload("stale"))), 0]
 [0.2, (to endpoint1 from peer1 : SessionReset(1)), 0]
 [0.3, (to endpoint1 from peer1 : SessionRetired(1)), 0]
 [0.4, (to endpoint1 from peer1 : SessionWire(2, payload("current"))), 0]
 [0.5, (to endpoint1 from local1 : ClientWrite(2, payload("before-reset"))), 0]
 [0.6, (to endpoint1 from peer1 : SessionReset(2)), 0]
 [0.7, (to endpoint1 from local1 : ClientWrite(2, payload("after-reset"))), 0]''',
    ))
    final = trace.split('result Config:', 1)[1]
    assert final.count('captured: SessionDelivery(2,') == 1
    assert '"stale"' not in final
    assert 'captured: SessionExpired' not in final
    assert final.count('captured: WriteAccepted(2,') == 1
    assert final.count('captured: WriteRejected(2,') == 1
    assert 'sessionLive: false' in final
    assert 'socketBroken: true' in final


def test_owned_sessions_keep_idle_deadlines_per_endpoint(tmp_path):
    trace = run_maude(tmp_path, session_scenario(
        {'local1': 'liveEndpoint(endpoint1, local1, peer1, false) '
                   'liveEndpoint(endpoint2, local1, peer2, false)'},
        '''[1.0, (to endpoint1 from endpoint1 : SessionCheck(2)), 0]
 [1.0, (to endpoint2 from endpoint2 : SessionCheck(2)), 0]
 [25.0, (to endpoint2 from peer2 : SessionWire(2, payload("activity"))), 0]''',
        end=33.0, server=True,
    ))
    final = trace.split('result Config:', 1)[1]
    assert final.count('captured: SessionExpired(peer1, 2)') == 1
    assert 'captured: SessionExpired(peer2, 2)' not in final
    assert 'captured: PrivMsgRes' in final


def test_one_hundred_clients_need_no_additional_session_actors(tmp_path):
    # Primary and backup connections need four records per client. Client-side
    # records live on existing clients; server-side records on their servers.
    clients = '\n'.join(
        f'withIrcSessions(mkIrcClient-v2(client({client}), endpoint({4 * client}), '
        f'"client{client}"), '
        + ' '.join(
            f'mkIrcSessionEndpoint(endpoint({4 * client + offset}), client({client}), '
            f'endpoint({4 * client + offset + 1}), true, client({client}))'
            for offset in (0, 2)
        ) + ')'
        for client in range(100)
    )
    servers = '\n'.join(
        f'withIrcSessions(mkIrcServer(server({server})), '
        + ' '.join(
            f'mkIrcSessionEndpoint(endpoint({4 * client + 2 * server + 1}), '
            f'server({server}), endpoint({4 * client + 2 * server}), '
            f'false, client({client}))'
            for client in range(100)
        ) + ')'
        for server in range(2)
    )
    trace = run_maude(tmp_path, f'''sload "{IRC / 'cp4_test_topology.maude'}"
mod OWNED-SESSION-SCALE-TEST is
 inc IRC-CP4-TEST-TOPOLOGY .
 ops endpoint client server : Nat -> Address [ctor] .
endm
rew run({{0.0 | nil}} rCtr(10) {clients} {servers}, 0.0) .
quit
''')
    final = trace.split('result Config:', 1)[1]
    assert final.count(' : IrcClient |') == 100
    assert final.count(' : IrcServer |') == 2
    assert final.count('sessionEndpoint(') == 400
    assert ': IrcSessionManager' not in final
    assert ': IrcSessionIface' not in final


@pytest.mark.parametrize('maker', [
    'mkIrcClient(ircCAd1, ifc1p)',
    'mkIrcClient(ircCAd1, ifc1p, "legacy")',
    'mkIrcClient(ircCAd1, ifc1p, "legacy", nilIMD)',
    'mkIrcClient-v2(ircCAd1, ifc1p, "legacy")',
    'mkIrcClient-cp4(ircCAd1, ifc1p, "cp4", emptyIrcChannelNameList)',
    'mkIrcClient-cp4(ircCAd1, ifc1p, "cp4", emptyIrcChannelNameList, 120.0, 120.0)',
    'mkIrcClient-cp4(ircCAd1, ifc1p, "cp4", emptyIrcChannelNameList, 120.0, 120.0, nilIMD)',
])
def test_all_client_makers_can_complete_session_registration(tmp_path, maker):
    trace = run_maude(tmp_path, f'''sload "{IRC / 'cp4_test_topology.maude'}"
set print attribute on .
rew run({{0.0 | nil}} rCtr(10)
 withIrcSessions({maker},
   mkIrcSessionEndpoint(ifc1p, ircCAd1, ifs1c1, true, ircCAd1))
 withIrcSessions(mkIrcServer(ircSAd1),
   mkIrcSessionEndpoint(ifs1c1, ircSAd1, ifc1p, false, ircCAd1))
 [0.0, (to ircCAd1 from ircCAd1 : ClientStartConnect), 0], 2.0) .
quit
''')
    final = trace.split('result Config:', 1)[1]
    assert 'initiating connection to server idx 0 (epoch 1)' in trace
    assert 'connState: connected' in final
    assert 'channelsReady: true' in final
    assert 'rttCount: 3' in final
    assert 'sendQueue: emptySendQueue' in final


def test_legacy_scheduled_send_completes_through_stateless_adapter(tmp_path):
    trace = run_maude(tmp_path, f'''sload "{IRC / 'cp4_test_topology.maude'}"
set print attribute on .
rew run({{0.0 | nil}} rCtr(10) ircMonitor
 mkIrcClient(ircCAd1, ifc1p, "legacy", imd(0.1, "#chat", 8) :: nilIMD)
 mkIrcServer(ircSAd1)
 mkIrcByteSeqIface(ifc1p, ircCAd1, ifs1c1)
 mkIrcByteSeqIface(ifs1c1, ircSAd1, ifc1p)
 [0.1, (to ircCAd1 from ircCAd1 : SendScheduledChat), 0], 1.0) .
quit
''')
    assert trace.count('send completed') == 1
    assert 'IrcIface ifc1p transforms PrivMsgReq' in trace
    final = trace.split('result Config:', 1)[1]
    assert 'sendQueue: emptySendQueue' in final
    assert 'writePending: false' in final


def test_shared_translator_preserves_independent_server_links(tmp_path):
    trace = run_maude(tmp_path, f'''sload "{IRC / 'cp4_test_topology.maude'}"
mod SHARED-TRANSLATOR-TEST is
 inc IRC-CP4-TEST-TOPOLOGY .
 ops source target first second firstPeer secondPeer : -> Address .
 op captured:_ : Content -> Attribute [ctor] .
 op ReceivedFrom : Address IrcMsg -> Content [ctor] .
 rl [capture-peer-delivery]:
   < target : IrcServer | attrs:AttributeSet >
   {{time:Float, (to target from endpoint:Address : message:IrcMsg)}}
  =>
   < target : IrcServer | attrs:AttributeSet,
     captured: ReceivedFrom(endpoint:Address, message:IrcMsg) > .
endm
set print attribute on .
rew run({{0.0 | nil}} rCtr(10) ircMonitor
 withIrcLinks(< source : IrcServer | noneAS >,
   mkIrcLinkEndpoint(first, source, firstPeer)
   mkIrcLinkEndpoint(second, source, secondPeer))
 withIrcLinks(< target : IrcServer | noneAS >,
   mkIrcLinkEndpoint(firstPeer, target, first)
   mkIrcLinkEndpoint(secondPeer, target, second))
 mkDisconnect(0.0, first, firstPeer)
 [0.1, (to first from source : PrivMsgReq(makeIrcChannelName("#chat"),
   makeIrcUserName(ircCAd1), "partitioned", source)), 0]
 [0.1, (to second from source : PrivMsgReq(makeIrcChannelName("#chat"),
   makeIrcUserName(ircCAd1), "reachable", source)), 0], 1.0) .
quit
''')
    final = trace.split('result Config:', 1)[1]
    assert final.count('captured: ReceivedFrom(secondPeer,') == 1
    assert '"reachable"' in final
    assert '"partitioned"' not in final
    assert ': IrcByteSeqIface' not in final
