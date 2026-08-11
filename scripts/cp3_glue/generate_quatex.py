import sys

WINDOW_SIZE = 900
SLIDING_WINDOW_SIZE = 60
BIN_SIZE = 10
HCS_DELAY = 0
MAX_WIN = 12

# WINDOW_SIZE = 60
# SLIDING_WINDOW_SIZE = 60
# BIN_SIZE = 10
# HCS_DELAY = 0
# MAX_WIN = 2

VANTAGES = [
   "ixpN",
   "masN",
   "dnsN",
   "minN",
   "srvN",
   "cl[1]",
   "cl[2]",
   "cl[3]",
   "cl[4]",
   "cl[5]",
]

CLIENTS = [
   "wtCl1IrcAddr",
   "wtCl2IrcAddr",
   "skyCl3IrcAddr",
   "skyCl4IrcAddr",
   "obfsCl5IrcAddr",
   "obfsCl6IrcAddr",
   "iodCl7IrcAddr",
   "iodCl8IrcAddr",
   "masCl9IrcAddr"
]

FEATS = {
    "dnsQueryRate": "dns_query_rate",
    "dnsQuerySize": "dns_query_size_mean",
    "dnsRespSize": "dns_response_size_mean",
    "tcpUpRate": "tcp_upload_rate",
    "tcpDownRate": "tcp_download_rate",
    "tcpUpToDownRate": "tcp_upload_download_ratio",
    "tcpOutPktRate": "tcp_outgoing_packet_rate",
    "tcpInPktRate": "tcp_incoming_packet_rate",
    "tcpOutToInPktRate": "tcp_packet_upload_download_ratio",
    "tcpPktSizeStdDev": "packet_size_std_dev",
    "tcpPktSize": "packet_size_mean",
    "tcpPktInterarrival": "packet_interarrival_mean",
    "tcpDirectionChange": "direction_change_count",
    "tcpActiveFlow": "active_flow_count",
    "tcpNewCnx": "tcp_new_conn_count",
}

CLIENT_MAP = {}

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

def int_to_float_str(i: int) -> str:
   return f"{i:.1f}"
   
def get_prefix_start_end(win: int, cum: bool) -> tuple[str, int, int]:
    if cum:
        prefix = "cumulative"
        start = 0
        end = (win+1) * WINDOW_SIZE
    else:
        prefix = "independent"
        start = win * WINDOW_SIZE
        end = (win+1) * WINDOW_SIZE
    return (prefix, start + HCS_DELAY, end + HCS_DELAY)

def mk_latency_query_chunk(win: int, cum: bool) -> Lines:
    prefix, i_start, i_end = get_prefix_start_end(win, cum)
    start, end = int_to_float_str(i_start), int_to_float_str(i_end)
    return Lines(
        f'eval E[s.rval("getMinLatency(getMonitor(C), {start}, {end})")]; // {prefix} latency0 {i_start} {i_end}',
        f'eval E[s.rval("getPercentileLatency(getMonitor(C), {start}, {end}, 25)")]; // {prefix} latency25 {i_start} {i_end}',
        f'eval E[s.rval("getPercentileLatency(getMonitor(C), {start}, {end}, 50)")]; // {prefix} latency50 {i_start} {i_end}',
        f'eval E[s.rval("getPercentileLatency(getMonitor(C), {start}, {end}, 75)")]; // {prefix} latency75 {i_start} {i_end}',
        f'eval E[s.rval("getMaxLatency(getMonitor(C), {start}, {end})")]; // {prefix} latency100 {i_start} {i_end}',
        f'eval E[s.rval("getGoodput(getMonitor(C), {start}, {end})")]; // {prefix} goodput {i_start} {i_end}',
    )

def mk_global_integrity_chunk(win: int, cum: bool) -> Lines:
    prefix, i_start, i_end = get_prefix_start_end(win, cum)
    start, end = int_to_float_str(i_start), int_to_float_str(i_end)
    return Lines(
        f'eval E[s.rval("getSystemIntegrity(getMonitor(C), getIrcSrv(C), {start}, {end})")]; // {prefix} integrity {i_start} {i_end}',
    )
   
def mk_client_integrity_chunk(win: int, cum: bool, client: str) -> Lines:
    prefix, i_start, i_end = get_prefix_start_end(win, cum)
    start, end = int_to_float_str(i_start), int_to_float_str(i_end)
    tne_client_name = CLIENT_MAP.get(client, client)
    return Lines(
        f'eval E[s.rval("getClientIntegrity(getMonitor(C), getIrcSrv(C), {client}, {start}, {end})")]; // {prefix} integrity {i_start} {i_end} {tne_client_name}',
    )

def mk_availability_chunk(win: int, cum: bool) -> Lines:
    prefix, i_start, i_end = get_prefix_start_end(win, cum)
    start, end = int_to_float_str(i_start), int_to_float_str(i_end)
    return Lines(
        f'eval E[s.rval("getMTBF(getMonitor(C), 16.0, {start}, {end})")]; // {prefix} availability {i_start} {i_end}',
    )

def mk_vantage_point_chunk(win: int, cum: bool, vantage: str, feat: str, tag_name: str) -> Lines:
    prefix, i_start, i_end = get_prefix_start_end(win, cum)
    start, end = int_to_float_str(i_start), int_to_float_str(i_end)
    slide_win = f"{SLIDING_WINDOW_SIZE:.1f}"
    bin_size = f"{BIN_SIZE:.1f}"
    tag = f'// {prefix} {tag_name} {i_start} {i_end} {vantage}'
    return Lines(
        f'eval E[s.rval("getCUSUM (getAdversary(C), {vantage}, {feat}, {start}, {end}, {slide_win}, {bin_size})]; {tag}'
    )

def all_queries() -> Lines:
    win_range = range(MAX_WIN)
    bool_range = [True, False]
    FEATS = {
    }

    return Lines(
       *[mk_latency_query_chunk(win, b) for win in win_range for b in bool_range],
       *[mk_global_integrity_chunk(win, b) for win in win_range for b in bool_range],
       *[mk_client_integrity_chunk(win, b, client) for win in win_range for b in bool_range for client in CLIENTS],
       *[mk_availability_chunk(win, b) for win in win_range for b in bool_range],
       *[mk_vantage_point_chunk(win, b, vant, feat, tag)
            for win in win_range
            for b in bool_range
            for vant in VANTAGES
            for (feat, tag) in FEATS.items()],
    )

if __name__ == "__main__":
    output_file = sys.argv[1]

    lines = Lines(
        all_queries()
    )

    with open(output_file, "w") as f:
       f.write('\n'.join(lines.lines))