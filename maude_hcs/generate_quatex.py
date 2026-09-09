import sys
from dataclasses import dataclass
from pathlib import Path

# WINDOW_SIZE = 60
# SLIDING_WINDOW_SIZE = 60
# BIN_SIZE = 10
# HCS_DELAY = 0
# MAX_WIN = 2

# ['dnsQueryRate', 'tcpOutPktRate', 'tcpInPktRate', 'tcpOutToInPktRate', 'tcpPktSizeStdDev', 'tcpPktSize', 'tcpPktInterarrival', 'tcpDirectionChange']
# ['ixpN', 'cl[1]', 'cl[2]', 'cl[3]', 'cl[4]', 'cl[5]', 'srvN', 'masN']
# ['wtCl1IrcAddr', 'wtCl2IrcAddr', 'skyCl3IrcAddr', 'skyCl4IrcAddr', 'obfsCl5IrcAddr', 'obfsCl6IrcAddr', 'iodCl7IrcAddr', 'iodCl8IrcAddr', 'masCl9IrcAddr']

FEATS = {
    "dnsQueryRate": "dns_query_rate",
    # "dnsQuerySize": "dns_query_size_mean",
    # "dnsRespSize": "dns_response_size_mean",
    # "tcpUpRate": "tcp_upload_rate",
    # "tcpDownRate": "tcp_download_rate",
    # "tcpUpToDownRate": "tcp_upload_download_ratio",
    "tcpOutPktRate": "tcp_outgoing_packet_rate",
    "tcpInPktRate": "tcp_incoming_packet_rate",
    "tcpOutToInPktRate": "tcp_packet_upload_download_ratio",
    "tcpPktSizeStdDev": "packet_size_std_dev",
    "tcpPktSize": "packet_size_mean",
    "tcpPktInterarrival": "packet_interarrival_mean",
    "tcpDirectionChange": "direction_change_count",
    # "tcpActiveFlow": "active_flow_count",
    # "tcpNewCnx": "tcp_new_conn_count",
}

VANTAGES = [
   "ixpN",
   "masN",
#    "dnsN",
#    "minN",
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

@dataclass
class Config:
    feats: dict[str, str]
    vants: list[str]
    clients: list[str]

    window_size: int = 900
    sliding_window_size: int = 60
    bin_size: int = 10
    hcs_delay: int = 0
    max_win: int = 12

    perf_only: bool = False
    conf_only: bool = False

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

  def __str__(self):
     return '\n'.join(self.lines)

def int_to_float_str(i: int) -> str:
   return f"{i:.1f}"
   
def get_prefix_start_end(cfg: Config, win: int, cum: bool) -> tuple[str, int, int]:
    if cum:
        prefix = "cumulative"
        start = 0
        end = (win+1) * cfg.window_size
    else:
        prefix = "independent"
        start = win * cfg.window_size
        end = (win+1) * cfg.window_size
    return (prefix, start + cfg.hcs_delay, end + cfg.hcs_delay)

def mk_latency_query_chunk(cfg: Config, win: int, cum: bool) -> Lines:
    if cfg.conf_only:
        return Lines()
    prefix, i_start, i_end = get_prefix_start_end(cfg, win, cum)
    start, end = int_to_float_str(i_start), int_to_float_str(i_end)
    if win == 0 and not cum:
        # this indep is a duplicate of cum 
        print(f"skipping independent win {win}: {prefix}")
        return Lines()
    return Lines(
        f'eval E[s.rval("getMinLatency(getMonitor(C), {start}, {end})")]; // {prefix} latency0 {i_start} {i_end}',
        f'eval E[s.rval("getPercentileLatency(getMonitor(C), {start}, {end}, 25)")]; // {prefix} latency25 {i_start} {i_end}',
        f'eval E[s.rval("getPercentileLatency(getMonitor(C), {start}, {end}, 50)")]; // {prefix} latency50 {i_start} {i_end}',
        f'eval E[s.rval("getPercentileLatency(getMonitor(C), {start}, {end}, 75)")]; // {prefix} latency75 {i_start} {i_end}',
        f'eval E[s.rval("getMaxLatency(getMonitor(C), {start}, {end})")]; // {prefix} latency100 {i_start} {i_end}',
        f'eval E[s.rval("getGoodput(getMonitor(C), {start}, {end})")]; // {prefix} goodput {i_start} {i_end}',
    )

def mk_global_integrity_chunk(cfg: Config, win: int, cum: bool) -> Lines:
    if cfg.conf_only:
        return Lines()
    prefix, i_start, i_end = get_prefix_start_end(cfg, win, cum)
    start, end = int_to_float_str(i_start), int_to_float_str(i_end)
    if win == 0 and not cum:
        # this indep is a duplicate of cum 
        print(f"skipping independent win {win}: {prefix}")
        return Lines()
    return Lines(
        f'eval E[s.rval("getSystemIntegrity(getMonitor(C), getIrcSrv(C), {start}, {end})")]; // {prefix} integrity {i_start} {i_end}',
    )
   
def mk_client_integrity_chunk(cfg: Config, win: int, cum: bool, client: str) -> Lines:
    if cfg.conf_only:
        return Lines()
    prefix, i_start, i_end = get_prefix_start_end(cfg, win, cum)
    start, end = int_to_float_str(i_start), int_to_float_str(i_end)
    if win == 0 and not cum:
        # this indep is a duplicate of cum 
        print(f"skipping independent win {win}: {prefix}")
        return Lines()
    return Lines(
        f'eval E[s.rval("getClientIntegrity(getMonitor(C), getIrcSrv(C), {client}, {start}, {end})")]; // {prefix} integrity {i_start} {i_end} {client}',
    )

def mk_availability_chunk(cfg: Config, win: int, cum: bool) -> Lines:
    if cfg.conf_only:
        return Lines()
    prefix, i_start, i_end = get_prefix_start_end(cfg, win, cum)
    start, end = int_to_float_str(i_start), int_to_float_str(i_end)
    if win == 0 and not cum:
        # this indep is a duplicate of cum 
        print(f"skipping independent win {win}: {prefix}")
        return Lines()
    return Lines(
        f'eval E[s.rval("getMTBF(getMonitor(C), 16.0, {start}, {end})")]; // {prefix} availability {i_start} {i_end}',
    )

def mk_vantage_point_chunk(cfg: Config, win: int, cum: bool, vantage: str, feat: str, tag_name: str) -> Lines:
    if cfg.perf_only:
       return Lines()
    prefix, i_start, i_end = get_prefix_start_end(cfg, win, cum)
    start, end = int_to_float_str(i_start), int_to_float_str(i_end)
    slide_win = f"{cfg.sliding_window_size:.1f}"
    bin_size = f"{cfg.bin_size:.1f}"
    tag = f'// {prefix} {tag_name} {i_start} {i_end} {vantage}'
    if win == 0 and not cum:
       # this indep is a duplicate of cum 
       print(f"skipping independent win {win}: {tag}")
       return Lines()
    return Lines(
        f'eval E[s.rval("getCUSUMZt(getAdversary(C), {vantage}, {feat}, {start}, {end}, {slide_win}, {bin_size})")]; {tag}'
    )

def all_queries(cfg: Config) -> Lines:
    win_range = range(cfg.max_win)
    bool_range = [True, False]

    return Lines(
       *[mk_latency_query_chunk(cfg, win, b) for win in win_range for b in bool_range],
       *[mk_global_integrity_chunk(cfg, win, b) for win in win_range for b in bool_range],
       *[mk_client_integrity_chunk(cfg, win, b, client) for win in win_range for b in bool_range for client in cfg.clients],
       *[mk_availability_chunk(cfg, win, b) for win in win_range for b in bool_range],
       *[mk_vantage_point_chunk(cfg, win, b, vant, feat, tag)
            for win in win_range
            for b in bool_range
            for vant in cfg.vants
            for (feat, tag) in cfg.feats.items()],
    )

def write_all_queries_to_file(cfg: Config, path: Path):
    with open(path, "w") as f:
       f.write(str(all_queries(cfg)))

if __name__ == "__main__":
    output_file = sys.argv[1]
    cfg = Config(FEATS, VANTAGES, CLIENTS, hcs_delay=10, max_win=4)
    write_all_queries_to_file(cfg, Path(output_file))