from .binance import BinanceAdapter
from .bybit import BybitAdapter
from .okx import OKXAdapter
from .bitget import BitgetAdapter
from .kucoin import KuCoinAdapter
from .mxc import MXCAdapter

ADAPTER_REGISTRY = {
    "binance": BinanceAdapter,
    "bybit": BybitAdapter,
    "okx": OKXAdapter,
    "bitget": BitgetAdapter,
    "kucoin": KuCoinAdapter,
    "mxc": MXCAdapter,
}
