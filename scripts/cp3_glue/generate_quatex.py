import sys

WINDOW_SIZE = 900
SLIDING_WINDOW_SIZE = 60
BIN_SIZE = 10
HCS_DELAY = 0
TGEN_DELAY = 0
BASELINE_LENGTH = 7200
MAX_WIN = 12

VISBILITY_MAP = {}
CLIENTS = ["testClient"]

# I should probably rewrite this to have long unbroken chunks that don't change except for windows. I think that would be most straightforward to go through.
# In any case the formatter should accept any ordering I think.
# ok let's try running this quatex with that little runscript I had Friday.
# Careful about floats, they break if decimal missing

class Lines:
  def __init__(self, *args, indent=0):
    lines = []
    for arg in args:
      if isinstance(arg, Lines):
        lines += arg.lines
      else:
        lines += [str(arg)]
    self.lines = [(" " * (indent*4)) + line for line in lines]

  def join(self, other):
    return Lines(*(self.lines + other.lines))

  def indent(self, indent=1):
    return Lines(*self.lines, indent=indent)

def get_prefix_and_start(win: int, cum: bool) -> tuple[str, str]:
    if cum:
        prefix = 'Cumulative'
        start = f"{0:.1f}"
    else:
        prefix = 'Independent'
        start = f"{win * WINDOW_SIZE:.1f}"
    return (prefix, start)

def mk_latency_query_chunk(win: int, cum: bool) -> Lines:
    prefix, start = get_prefix_and_start(win, cum)
    end = f'{(win+1) * WINDOW_SIZE:.1f}'

    return Lines(
        f'{prefix}Latency0Win{win}() = s.rval("getMinLatency(getMonitor(C), {start}, {end})");',
        f'{prefix}Latency25Win{win}() = s.rval("getPercentileLatency(getMonitor(C), {start}, {end}, 25)");',
        f'{prefix}Latency50Win{win}() = s.rval("getPercentileLatency(getMonitor(C), {start}, {end}, 50)");',
        f'{prefix}Latency75Win{win}() = s.rval("getPercentileLatency(getMonitor(C), {start}, {end}, 75)");',
        f'{prefix}Latency100Win{win}() = s.rval("getMaxLatency(getMonitor(C), {start}, {end})");',
        f'{prefix}GoodputWin{win}() = s.rval("getGoodput(getMonitor(C), {start}, {end})");',
        f'eval E[{prefix}Latency0Win{win}()];',
        f'eval E[{prefix}Latency25Win{win}()];',
        f'eval E[{prefix}Latency50Win{win}()];',
        f'eval E[{prefix}Latency75Win{win}()];',
        f'eval E[{prefix}Latency100Win{win}()];',
        f'eval E[{prefix}GoodputWin{win}()];',
    )

def mk_global_integrity_query_chunk(win: int, cum: bool) -> Lines:
    prefix, start = get_prefix_and_start(win, cum)
    end = (win+1) * WINDOW_SIZE

    return Lines(
        f'{prefix}IntegrityWin{win}() = s.rval("getSystemIntegrity(getMonitor(C), getIrcSrv(C), {start}, {end})");',
        f'eval E[{prefix}IntegrityWin{win}()] ;',
    )
   
def mk_client_integrity_chunk(win: int, cum: bool, client: str) -> Lines:
    prefix, start = get_prefix_and_start(win, cum)
    end = (win+1) * WINDOW_SIZE

    return Lines(
        f'{prefix}ClientIntegrity{client}Win{win}() = s.rval("getClientIntegrity(getMonitor(C), getIrcSrv(C), {client}, {start}, {end})");',
        f'eval E[{prefix}ClientIntegrity{client}Win{win}()] ;',
    )

def all_latency_queries() -> Lines:
    return Lines(
       *[mk_latency_query_chunk(win, False) for win in range(MAX_WIN)],
       *[mk_latency_query_chunk(win, True) for win in range(MAX_WIN)],
    )

def all_integrity_queries() -> Lines:
    return Lines(
       *[mk_global_integrity_query_chunk(win, False) for win in range(MAX_WIN)],
       *[mk_client_integrity_chunk(win, False, client) for win in range(MAX_WIN) for client in CLIENTS],
       *[mk_global_integrity_query_chunk(win, True) for win in range(MAX_WIN)],
       *[mk_client_integrity_chunk(win, True, client) for win in range(MAX_WIN) for client in CLIENTS],
    )
   
# f'///////////////',
# f'// Integrity ',
# f'///////////////',
# f'',
# f'// getSystemIntegrity (monitor, irc_server, Tstart, Tend)',
# f'// getClientIntegrity (monitor, irc_server, client, Tstart, Tend)',
# f'',
# f'Integrity() = s.rval("getSystemIntegrity(getMonitor(C), getIrcSrv(C), 0.0, 1000.0)");',
# f'IntegrityClient() = s.rval("getClientIntegrity(getMonitor(C), getIrcSrv(C), wtCl1IrcAddr, 0.0, 1000.0)");',
# f'',
# f'eval E[Integrity()] ;',
# f'// eval E[IntegrityClient()] ;',
# f'',
# f'///////////////',
# f'// Availabolity',
# f'///////////////',
# f'',
# f'// getMTBF (monitor, irc_server, Tn, Tstart, Tend)',
# f'',
# f'MTBF() = s.rval("getMTBF(getMonitor(C), 16.0, 0.0, 1000.0)");',
# f'',
# f'eval E[MTBF()] with delta = 2 ;',
# f'',
# f'//////////////////',
# f'// Confidentiality ',
# f'//////////////////',
# f'',
# f'// getCUSUM (adversary, vantage_point, feature, Tstart, Tend, window_size (seconds), bin_size (seconds), baselineCDF, K) ',
# f'// getBaselineCDF(baseline, vantage_point, feature, baseline Tstart, baseline Tend, bin_size) ',
# f'// getBaselineK(baseline, vantage_point, feature, baseline Tstart, baseline Tend, window_size, bin_size) ',
# f'',
# f'// Cumulative t0_15 : Tstart = 0.0, Tend = 900.0, offset by hcsDelay ',
# f'// Cumulative t0_30 : Tstart = 0.0, Tend = 1800.0, offset by hcsDelay  ',
# f'',
# f'// feature : dnsQueryRate dnsQuerySize dnsRespSize tcpUpRate tcpDownRate tcpUpToDownRate tcpOutPktRate tcpInPktRate tcpOutToInPktRate tcpPktSizeStdDev tcpPktSize tcpPktInterarrival tcpDirectionChange tcpActiveFlow tcpNewCnx  ',
# f'',
# f'CumulativeCUSUMTcpOutPktRate() = s.rval("getCUSUM (getAdversary(C), ixpN, tcpOutPktRate, 100.0, 300.0, 60.0, 10.0, ',
# f'                                     getBaselineCDF(getBaseline(C), ixpN, tcpOutPktRate, 0.0, 100.0, 10.0), ',
# f'                                       getBaselineK(getBaseline(C), ixpN, tcpOutPktRate, 0.0, 100.0, 60.0, 10.0))");',
# f'',
# f'// srvN masN minN dnsN ixpN cl[i] in visibilityMap',
# f'',
# f'CumulativeCUSUMTcpOutPktRateSrvN() = s.rval("getCUSUM (getAdversary(C), srvN, tcpOutPktRate, 100.0, 300.0, 60.0, 10.0, ',
# f'                                         getBaselineCDF(getBaseline(C), srvN, tcpOutPktRate, 0.0, 100.0, 10.0), ',
# f'                                           getBaselineK(getBaseline(C), srvN, tcpOutPktRate, 0.0, 100.0, 60.0, 10.0))");',
# f'',
# f'// Independent t0_15 : Tstart = 0.0, Tend = 900.0, offset by hcsDelay ',
# f'// Independent t15_30 : Tstart = 900.0, Tend = 1800.0, offset by hcsDelay ',
# f'',
# f'IndependentCUSUMTcpOutPktRate() = s.rval("getCUSUM (getAdversary(C), ixpN, tcpOutPktRate, 100.0, 300.0, 60.0, 10.0, ',
# f'                                     getBaselineCDF(getBaseline(C), ixpN, tcpOutPktRate, 0.0, 100.0, 10.0), ',
# f'                                       getBaselineK(getBaseline(C), ixpN, tcpOutPktRate, 0.0, 100.0, 60.0, 10.0))");',
# f'',
# f'// eval E[CumulativeCUSUMDnsQueryRate()] ;',
# f'// eval E[CumulativeCUSUMDnsQuerySize()] ;',
# f'// eval E[CumulativeCUSUMDnsRespSize()] ;',
# f'// eval E[CumulativeCUSUMTcpUpRate()] ;',
# f'// eval E[CumulativeCUSUMTcpDownRate()] ;',
# f'// eval E[CumulativeCUSUMTcpUpToDownRate()] ;',
# f'// eval E[CumulativeCUSUMTcpOutPktRate()] ;',
# f'// eval E[CumulativeCUSUMTcpInPktRate()] ;',
# f'// eval E[CumulativeCUSUMTcpOutToInPktRate()] ;',
# f'// eval E[CumulativeCUSUMTcpPktSizeStdDev()] ;',
# f'// eval E[CumulativeCUSUMTcpPktSize()] ;',
# f'// eval E[CumulativeCUSUMTcpPktInterarrival()] ;',
# f'// eval E[CumulativeCUSUMTcpDirectionChange()] ;',
# f'// eval E[CumulativeCUSUMTcpActiveFlow()] ;',
# f'// eval E[CumulativeCUSUMTcpNewCnx()] ;',
# f'',
# f'// eval E[CumulativeCUSUMTcpOutPktRateSrvN()] ;',
# f'',
# f'// eval E[IndependentCUSUMDnsQueryRate()] ;',
# f'// eval E[IndependentCUSUMDnsQuerySize()] ;',
# f'// eval E[IndependentCUSUMDnsRespSize()] ;',
# f'// eval E[IndependentCUSUMTcpUpRate()] ;',
# f'// eval E[IndependentCUSUMTcpDownRate()] ;',
# f'// eval E[IndependentCUSUMTcpUpToDownRate()] ;',
# f'// eval E[IndependentCUSUMTcpOutPktRate()] ;',
# f'// eval E[IndependentCUSUMTcpInPktRate()] ;',
# f'// eval E[IndependentCUSUMTcpOutToInPktRate()] ;',
# f'// eval E[IndependentCUSUMTcpPktSizeStdDev()] ;',
# f'// eval E[IndependentCUSUMTcpPktSize()] ;',
# f'// eval E[IndependentCUSUMTcpPktInterarrival()] ;',
# f'// eval E[IndependentCUSUMTcpDirectionChange()] ;',
# f'// eval E[IndependentCUSUMTcpActiveFlow()] ;',
# f'// eval E[IndependentCUSUMTcpNewCnx()] ;',
# f'',
# f'//  from pwnd-cp3/src/adversary/configs/thresholds.json',
# f'//  "dns_query_rate": 2.5,',
# f'//  "dns_query_size_mean": 2.5,',
# f'//  "dns_response_size_mean": 2.5,',
# f'//  "tcp_upload_rate": 3.5,',
# f'//  "tcp_download_rate": 3.5,',
# f'//  "tcp_upload_download_ratio": 5.0,',
# f'//  "tcp_outgoing_packet_rate": 3.5,',
# f'//  "tcp_incoming_packet_rate": 3.5,',
# f'//  "tcp_packet_upload_download_ratio": 5.0,',
# f'//  "packet_size_std_dev": 4.0,',
# f'//  "packet_size_mean": 3.0,',
# f'//  "packet_interarrival_mean": 3.0,',
# f'//  "direction_change_count": 4.0,',
# f'//  "active_flow_count": 2.5,',
# f'//  "tcp_new_conn_count": 3.5',
# f'',
# f'// getToD (adversary, vantage_point, feature, Tstart, Tend, window_size (seconds), bin_size (seconds), threshold) ',
# f'// getToD (adversary, vantage_point, feature, Tstart, Tend, window_size (seconds), bin_size (seconds), threshold, baselineCDF, K) ',
# f'',
# f'ToDDnsQueryRate() = s.rval("getToD (getAdversary(C), ixpN, dnsQueryRate, 100.0, 300.0, 60.0, 10.0, dns_query_rate)");',
# f'ToDDnsQuerySize() = s.rval("getToD (getAdversary(C), ixpN, dnsQuerySize, 100.0, 300.0, 60.0, 10.0, dns_query_size_mean)");',
# f'ToDDnsRespSize() = s.rval("getToD (getAdversary(C), ixpN, dnsRespSize, 100.0, 300.0, 60.0, 10.0, dns_response_size_mean)");',
# f'ToDTcpUpRate() = s.rval("getToD (getAdversary(C), ixpN, tcpUpRate, 100.0, 300.0, 60.0, 10.0, tcp_upload_rate)");',
# f'ToDTcpDownRate() = s.rval("getToD (getAdversary(C), ixpN, tcpDownRate, 100.0, 300.0, 60.0, 10.0, tcp_download_rate)");',
# f'ToDTcpUpToDownRate() = s.rval("getToD (getAdversary(C), ixpN, tcpUpToDownRate, 100.0, 300.0, 60.0, 10.0, tcp_upload_download_ratio)");',
# f'ToDTcpOutPktRate() = s.rval("getToD (getAdversary(C), ixpN, tcpOutPktRate, 100.0, 300.0, 60.0, 10.0, tcp_outgoing_packet_rate)");',
# f'ToDTcpInPktRate() = s.rval("getToD (getAdversary(C), ixpN, tcpInPktRate, 100.0, 300.0, 60.0, 10.0, tcp_incoming_packet_rate)");',
# f'ToDTcpOutToInPktRate() = s.rval("getToD (getAdversary(C), ixpN, tcpOutToInPktRate, 100.0, 300.0, 60.0, 10.0, tcp_packet_upload_download_ratio)");',
# f'ToDTcpPktSizeStdDev() = s.rval("getToD (getAdversary(C), ixpN, tcpPktSizeStdDev, 100.0, 300.0, 60.0, 10.0, packet_size_std_dev)");',
# f'ToDTcpPktSize() = s.rval("getToD (getAdversary(C), ixpN, tcpPktSize, 100.0, 300.0, 60.0, 10.0, packet_size_mean)");',
# f'ToDTcpPktInterarrival() = s.rval("getToD (getAdversary(C), ixpN, tcpPktInterarrival, 100.0, 300.0, 60.0, 10.0, packet_interarrival_mean)");',
# f'ToDTcpDirectionChange() = s.rval("getToD (getAdversary(C), ixpN, tcpDirectionChange, 100.0, 300.0, 60.0, 10.0, direction_change_count)");',
# f'ToDTcpActiveFlow() = s.rval("getToD (getAdversary(C), ixpN, tcpActiveFlow, 100.0, 300.0, 60.0, 10.0, active_flow_count)");',
# f'ToDTcpNewCnx() = s.rval("getToD (getAdversary(C), ixpN, tcpNewCnx, 100.0, 300.0, 60.0, 10.0, tcp_new_conn_count)");',
# f'',
# f'// eval E[ToDDnsQueryRate()] ;',
# f'// eval E[ToDDnsQuerySize()] ;',
# f'// eval E[ToDDnsRespSize()] ;',
# f'// eval E[ToDTcpUpRate()] ;',
# f'// eval E[ToDTcpDownRate()] ;',
# f'// eval E[ToDTcpUpToDownRate()] ;',
# f'// eval E[ToDTcpOutPktRate()] ;',
# f'// eval E[ToDTcpInPktRate()] ;',
# f'// eval E[ToDTcpOutToInPktRate()] ;',
# f'// eval E[ToDTcpPktSizeStdDev()] ;',
# f'// eval E[ToDTcpPktSize()] ;',
# f'// eval E[ToDTcpPktInterarrival()] ;',
# f'// eval E[ToDTcpDirectionChange()] ;',
# f'// eval E[ToDTcpActiveFlow()] ;',
# f'// eval E[ToDTcpNewCnx()] ;',

if __name__ == "__main__":
    output_file = sys.argv[1]

    lines = Lines(
        all_latency_queries(),
        all_integrity_queries(),
    )

    with open(output_file, "w") as f:
       f.write('\n'.join(lines.lines))