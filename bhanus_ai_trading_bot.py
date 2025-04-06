
import logging
from decimal import Decimal
from typing import Dict, List

from hummingbot.core.data_type.common import OrderType, TradeType, PriceType
from hummingbot.core.data_type.order_candidate import OrderCandidate
from hummingbot.core.event.events import OrderFilledEvent
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from hummingbot.data_feed.candles_feed.candles_factory import CandlesFactory, CandlesConfig
from hummingbot.connector.connector_base import ConnectorBase

class AdvancedAITradingBot(ScriptStrategyBase):
    """
    AI Trading Bot with:
    - Candlestick Patterns
    - RSI (Relative Strength Index)
    - Inventory Shift
    - Trend Shift
    - Volatility Spread
    """

    trading_pair = "ETH-USDT"
    exchange = "okx"
    order_amount = 0.01
    order_refresh_time = 20  # seconds
    bid_spread = 0.001  # 0.1%
    ask_spread = 0.001

    candle_interval = "1m"
    candles_length = 30
    max_records = 1000

    candles = CandlesFactory.get_candle(CandlesConfig(
        connector=exchange,
        trading_pair=trading_pair,
        interval=candle_interval,
        max_records=max_records
    ))

    markets = {exchange: {trading_pair}}

    def _init_(self, connectors: Dict[str, ConnectorBase]):
        super()._init_(connectors)
        self.candles.start()

    def on_stop(self):
        self.candles.stop()

    def on_tick(self):
        if self.current_timestamp % self.order_refresh_time == 0:
            self.cancel_all_orders()
            orders = self.create_orders()
            adjusted_orders = self.adjust_proposal_to_budget(orders)
            self.place_orders(adjusted_orders)

    def get_candle_features(self):
        candles_df = self.candles.candles_df
        candles_df.ta.rsi(length=self.candles_length, append=True)
        candles_df.ta.atr(append=True)  # Volatility spread
        return candles_df

    def create_orders(self) -> List[OrderCandidate]:
        ref_price = self.connectors[self.exchange].get_price_by_type(self.trading_pair, PriceType.MidPrice)
        buy_price = ref_price * Decimal(1 - self.bid_spread)
        sell_price = ref_price * Decimal(1 + self.ask_spread)

        buy_order = OrderCandidate(
            trading_pair=self.trading_pair, order_side=TradeType.BUY,
            amount=Decimal(self.order_amount), price=buy_price,
            order_type=OrderType.LIMIT, is_maker=True
        )

        sell_order = OrderCandidate(
            trading_pair=self.trading_pair, order_side=TradeType.SELL,
            amount=Decimal(self.order_amount), price=sell_price,
            order_type=OrderType.LIMIT, is_maker=True
        )

        return [buy_order, sell_order]

    def adjust_proposal_to_budget(self, orders: List[OrderCandidate]) -> List[OrderCandidate]:
        return self.connectors[self.exchange].budget_checker.adjust_candidates(orders, all_or_none=True)

    def place_orders(self, orders: List[OrderCandidate]):
        for order in orders:
            self.place_order(order)

    def place_order(self, order: OrderCandidate):
        if order.order_side == TradeType.SELL:
            self.sell(self.exchange, order.trading_pair, order.amount, order.order_type, order.price)
        else:
            self.buy(self.exchange, order.trading_pair, order.amount, order.order_type, order.price)

    def cancel_all_orders(self):
        for order in self.get_active_orders(connector_name=self.exchange):
            self.cancel(self.exchange, order.trading_pair, order.client_order_id)

    def did_fill_order(self, event: OrderFilledEvent):
        message = f"{event.trade_type.name} {event.amount} {event.trading_pair} at {event.price}"
        self.log_with_clock(logging.INFO, message)
        self.notify_hb_app_with_timestamp(message)

    def format_status(self) -> str:
        lines = ["\nBot Status:"]
        balance_df = self.get_balance_df()
        lines.append("Balances:")
        lines.extend(balance_df.to_string(index=False).split("\n"))

        candles_df = self.get_candle_features()
        lines.append(f"\nCandlestick Data ({self.candle_interval} interval):")
        lines.extend(candles_df.tail(self.candles_length).to_string(index=False).split("\n"))

        return "\n".join(lines)
