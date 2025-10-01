"""
Order management system with automatic resubmission for limit orders
"""

import asyncio
import schedule
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from threading import Thread
import time

from .trading_engine import TradingEngine
from .logger import TradingLogger


class OrderResubmissionManager:
    """Manages automatic resubmission of unfilled limit orders"""
    
    def __init__(self, trading_engine: TradingEngine, 
                 resubmission_interval_minutes: int = 5):
        """
        Initialize order resubmission manager
        
        Args:
            trading_engine: Trading engine instance
            resubmission_interval_minutes: Interval between resubmission checks
        """
        self.trading_engine = trading_engine
        self.resubmission_interval = resubmission_interval_minutes
        self.logger = TradingLogger(__name__)
        
        self.running = False
        self.scheduler_thread: Optional[Thread] = None
        
        # Setup schedule
        schedule.every(self.resubmission_interval).minutes.do(self._check_orders_job)
        
        self.logger.info(f"Order resubmission manager initialized with {resubmission_interval_minutes} minute intervals")
    
    def start(self):
        """Start the order resubmission scheduler"""
        if self.running:
            self.logger.warning("Order resubmission manager is already running")
            return
        
        self.running = True
        
        def run_scheduler():
            """Run the scheduler in a separate thread"""
            self.logger.info("Starting order resubmission scheduler")
            
            while self.running:
                try:
                    schedule.run_pending()
                    time.sleep(1)
                except Exception as e:
                    self.logger.error(f"Scheduler error: {e}", exc_info=True)
        
        self.scheduler_thread = Thread(target=run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        self.logger.info("Order resubmission manager started")
    
    def stop(self):
        """Stop the order resubmission scheduler"""
        if not self.running:
            return
        
        self.running = False
        schedule.clear()
        
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        
        self.logger.info("Order resubmission manager stopped")
    
    def _check_orders_job(self):
        """Job function for checking and resubmitting orders"""
        try:
            self.logger.debug("Checking orders for resubmission")
            
            # Run the async check in the event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                loop.run_until_complete(self.trading_engine.check_and_resubmit_orders())
            finally:
                loop.close()
                
        except Exception as e:
            self.logger.error(f"Error in order resubmission check: {e}", exc_info=True)
    
    def force_check(self):
        """Force an immediate check for order resubmission"""
        self.logger.info("Forcing order resubmission check")
        self._check_orders_job()
    
    def get_status(self) -> Dict:
        """Get status of the order resubmission manager"""
        return {
            'running': self.running,
            'resubmission_interval_minutes': self.resubmission_interval,
            'pending_orders_count': len(self.trading_engine.pending_orders),
            'next_check': schedule.next_run().isoformat() if schedule.jobs else None
        }


class OrderMonitor:
    """Monitor for tracking order lifecycle and performance"""
    
    def __init__(self):
        """Initialize order monitor"""
        self.logger = TradingLogger(__name__)
        
        # Order statistics
        self.order_stats = {
            'total_orders': 0,
            'filled_orders': 0,
            'cancelled_orders': 0,
            'rejected_orders': 0,
            'resubmitted_orders': 0,
            'avg_fill_time_seconds': 0.0
        }
        
        # Order history
        self.order_history: List[Dict] = []
        self.max_history_size = 1000
    
    def record_order_placed(self, order_id: str, symbol: str, action: str, 
                          quantity: int, order_type: str, price: Optional[float] = None):
        """Record when an order is placed"""
        order_record = {
            'order_id': order_id,
            'symbol': symbol,
            'action': action,
            'quantity': quantity,
            'order_type': order_type,
            'price': price,
            'placed_time': datetime.utcnow(),
            'status': 'placed',
            'fill_time': None,
            'fill_price': None,
            'resubmission_count': 0
        }
        
        self._add_to_history(order_record)
        self.order_stats['total_orders'] += 1
        
        self.logger.info(f"Order recorded: {order_id} - {action} {quantity} {symbol}")
    
    def record_order_filled(self, order_id: str, fill_price: float, fill_time: datetime = None):
        """Record when an order is filled"""
        if fill_time is None:
            fill_time = datetime.utcnow()
        
        # Find and update order record
        for record in reversed(self.order_history):
            if record['order_id'] == order_id:
                record['status'] = 'filled'
                record['fill_time'] = fill_time
                record['fill_price'] = fill_price
                
                # Calculate fill time
                if record['placed_time']:
                    fill_duration = (fill_time - record['placed_time']).total_seconds()
                    self._update_avg_fill_time(fill_duration)
                
                break
        
        self.order_stats['filled_orders'] += 1
        self.logger.info(f"Order fill recorded: {order_id} at ${fill_price:.2f}")
    
    def record_order_cancelled(self, order_id: str):
        """Record when an order is cancelled"""
        # Find and update order record
        for record in reversed(self.order_history):
            if record['order_id'] == order_id:
                record['status'] = 'cancelled'
                break
        
        self.order_stats['cancelled_orders'] += 1
        self.logger.info(f"Order cancellation recorded: {order_id}")
    
    def record_order_rejected(self, order_id: str, reason: str = ""):
        """Record when an order is rejected"""
        # Find and update order record
        for record in reversed(self.order_history):
            if record['order_id'] == order_id:
                record['status'] = 'rejected'
                record['rejection_reason'] = reason
                break
        
        self.order_stats['rejected_orders'] += 1
        self.logger.info(f"Order rejection recorded: {order_id} - {reason}")
    
    def record_order_resubmitted(self, old_order_id: str, new_order_id: str):
        """Record when an order is resubmitted"""
        # Find and update old order record
        for record in reversed(self.order_history):
            if record['order_id'] == old_order_id:
                record['status'] = 'resubmitted'
                record['resubmitted_as'] = new_order_id
                record['resubmission_count'] += 1
                break
        
        self.order_stats['resubmitted_orders'] += 1
        self.logger.info(f"Order resubmission recorded: {old_order_id} → {new_order_id}")
    
    def _add_to_history(self, record: Dict):
        """Add record to history with size limit"""
        self.order_history.append(record)
        
        # Maintain history size limit
        if len(self.order_history) > self.max_history_size:
            self.order_history = self.order_history[-self.max_history_size:]
    
    def _update_avg_fill_time(self, fill_duration_seconds: float):
        """Update average fill time"""
        filled_count = self.order_stats['filled_orders']
        current_avg = self.order_stats['avg_fill_time_seconds']
        
        # Calculate new average
        new_avg = ((current_avg * (filled_count - 1)) + fill_duration_seconds) / filled_count
        self.order_stats['avg_fill_time_seconds'] = new_avg
    
    def get_statistics(self) -> Dict:
        """Get order statistics"""
        total = self.order_stats['total_orders']
        
        stats = self.order_stats.copy()
        
        if total > 0:
            stats['fill_rate'] = self.order_stats['filled_orders'] / total
            stats['cancellation_rate'] = self.order_stats['cancelled_orders'] / total
            stats['rejection_rate'] = self.order_stats['rejected_orders'] / total
            stats['resubmission_rate'] = self.order_stats['resubmitted_orders'] / total
        else:
            stats['fill_rate'] = 0.0
            stats['cancellation_rate'] = 0.0
            stats['rejection_rate'] = 0.0
            stats['resubmission_rate'] = 0.0
        
        return stats
    
    def get_recent_orders(self, limit: int = 50) -> List[Dict]:
        """Get recent order history"""
        return self.order_history[-limit:] if self.order_history else []
    
    def get_orders_by_symbol(self, symbol: str, limit: int = 50) -> List[Dict]:
        """Get order history for a specific symbol"""
        symbol_orders = [
            record for record in self.order_history 
            if record['symbol'] == symbol
        ]
        return symbol_orders[-limit:] if symbol_orders else []
    
    def get_performance_summary(self) -> Dict:
        """Get performance summary"""
        stats = self.get_statistics()
        
        return {
            'total_orders': stats['total_orders'],
            'success_rate': stats['fill_rate'],
            'avg_fill_time_minutes': stats['avg_fill_time_seconds'] / 60,
            'resubmission_rate': stats['resubmission_rate'],
            'last_24h_orders': self._count_orders_in_period(hours=24),
            'last_hour_orders': self._count_orders_in_period(hours=1)
        }
    
    def _count_orders_in_period(self, hours: int) -> int:
        """Count orders placed in the last N hours"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        count = 0
        for record in reversed(self.order_history):
            if record['placed_time'] >= cutoff_time:
                count += 1
            else:
                break  # History is ordered, so we can break early
        
        return count