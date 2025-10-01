"""
Webhook server to receive TradingView alerts
"""

import json
import hashlib
import hmac
from datetime import datetime
from typing import Dict, Any, Callable, Optional
from flask import Flask, request, jsonify
from threading import Thread
import logging

from .logger import TradingLogger


class WebhookServer:
    """Flask-based webhook server for receiving TradingView alerts"""
    
    def __init__(self, port: int, secret: str = "", allowed_ips: list = None):
        """
        Initialize webhook server
        
        Args:
            port: Port to run the server on
            secret: Optional secret for webhook authentication
            allowed_ips: List of allowed IP addresses (empty list allows all)
        """
        self.port = port
        self.secret = secret
        self.allowed_ips = allowed_ips or []
        self.logger = TradingLogger(__name__)
        
        # Create Flask app
        self.app = Flask(__name__)
        self.app.config['SECRET_KEY'] = secret or 'default-secret-key'
        
        # Callback function for processing alerts
        self.alert_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        
        # Setup routes
        self._setup_routes()
        
        # Server thread
        self.server_thread: Optional[Thread] = None
        self.running = False
    
    def _setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/webhook', methods=['POST'])
        def webhook():
            """Handle incoming webhook requests"""
            try:
                # Check IP whitelist
                if self.allowed_ips and request.remote_addr not in self.allowed_ips:
                    self.logger.warning(f"Rejected request from unauthorized IP: {request.remote_addr}")
                    return jsonify({'error': 'Unauthorized IP'}), 403
                
                # Verify content type
                if not request.is_json:
                    self.logger.warning("Received non-JSON request")
                    return jsonify({'error': 'Content-Type must be application/json'}), 400
                
                # Get request data
                data = request.get_json()
                if not data:
                    self.logger.warning("Received empty JSON data")
                    return jsonify({'error': 'Empty JSON data'}), 400
                
                # Verify webhook signature if secret is configured
                if self.secret:
                    signature = request.headers.get('X-Signature')
                    if not self._verify_signature(json.dumps(data, sort_keys=True), signature):
                        self.logger.warning("Invalid webhook signature")
                        return jsonify({'error': 'Invalid signature'}), 403
                
                # Log the received alert
                self.logger.alert_received(data)
                
                # Process the alert
                if self.alert_callback:
                    try:
                        self.alert_callback(data)
                        return jsonify({'status': 'success', 'message': 'Alert processed'}), 200
                    except Exception as e:
                        self.logger.error(f"Error processing alert: {e}", exc_info=True)
                        return jsonify({'error': 'Failed to process alert'}), 500
                else:
                    self.logger.warning("No alert callback configured")
                    return jsonify({'error': 'No alert processor configured'}), 500
                    
            except Exception as e:
                self.logger.error(f"Webhook error: {e}", exc_info=True)
                return jsonify({'error': 'Internal server error'}), 500
        
        @self.app.route('/health', methods=['GET'])
        def health():
            """Health check endpoint"""
            return jsonify({
                'status': 'healthy',
                'timestamp': datetime.utcnow().isoformat(),
                'version': '1.0.0'
            }), 200
        
        @self.app.route('/status', methods=['GET'])
        def status():
            """Status endpoint with basic information"""
            return jsonify({
                'status': 'running',
                'port': self.port,
                'timestamp': datetime.utcnow().isoformat(),
                'webhook_url': f'http://localhost:{self.port}/webhook',
                'health_url': f'http://localhost:{self.port}/health'
            }), 200
    
    def _verify_signature(self, payload: str, signature: str) -> bool:
        """
        Verify webhook signature
        
        Args:
            payload: JSON payload as string
            signature: Signature from X-Signature header
            
        Returns:
            True if signature is valid, False otherwise
        """
        if not signature:
            return False
        
        try:
            # Expected format: sha256=<hash>
            if not signature.startswith('sha256='):
                return False
            
            expected_signature = signature[7:]  # Remove 'sha256=' prefix
            
            # Calculate HMAC
            calculated_signature = hmac.new(
                self.secret.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Compare signatures
            return hmac.compare_digest(expected_signature, calculated_signature)
            
        except Exception as e:
            self.logger.error(f"Signature verification error: {e}")
            return False
    
    def set_alert_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """
        Set the callback function for processing alerts
        
        Args:
            callback: Function to call when an alert is received
        """
        self.alert_callback = callback
        self.logger.info("Alert callback configured")
    
    def start(self):
        """Start the webhook server"""
        if self.running:
            self.logger.warning("Webhook server is already running")
            return
        
        self.running = True
        
        def run_server():
            """Run the Flask server"""
            try:
                self.logger.info(f"Starting webhook server on port {self.port}")
                self.app.run(
                    host='0.0.0.0',
                    port=self.port,
                    debug=False,
                    use_reloader=False,
                    threaded=True
                )
            except Exception as e:
                self.logger.error(f"Failed to start webhook server: {e}", exc_info=True)
                self.running = False
        
        self.server_thread = Thread(target=run_server, daemon=True)
        self.server_thread.start()
        
        self.logger.info(f"Webhook server started on http://0.0.0.0:{self.port}")
        self.logger.info(f"Webhook endpoint: http://localhost:{self.port}/webhook")
        self.logger.info(f"Health check: http://localhost:{self.port}/health")
    
    def stop(self):
        """Stop the webhook server"""
        if not self.running:
            return
        
        self.running = False
        self.logger.info("Webhook server stopped")
    
    def is_running(self) -> bool:
        """Check if the server is running"""
        return self.running and self.server_thread and self.server_thread.is_alive()


class AlertParser:
    """Parser for TradingView alert messages"""
    
    @staticmethod
    def parse_alert(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse TradingView alert data into standardized format
        
        Expected TradingView alert format:
        {
            "action": "buy|sell|short|cover",
            "symbol": "AAPL",
            "quantity": 100,
            "price": 150.50,  # Optional
            "message": "Custom message",  # Optional
            "timestamp": "2024-01-01T10:00:00Z"  # Optional
        }
        
        Args:
            data: Raw alert data from TradingView
            
        Returns:
            Parsed alert data
        """
        parsed = {
            'action': None,
            'symbol': None,
            'quantity': None,
            'price': None,
            'message': '',
            'timestamp': datetime.utcnow().isoformat(),
            'raw_data': data
        }
        
        # Extract action
        action = data.get('action', '').lower().strip()
        if action in ['buy', 'sell', 'short', 'cover']:
            parsed['action'] = action
        else:
            raise ValueError(f"Invalid or missing action: {action}")
        
        # Extract symbol
        symbol = data.get('symbol', '').upper().strip()
        if not symbol:
            raise ValueError("Missing symbol")
        parsed['symbol'] = symbol
        
        # Extract quantity
        quantity = data.get('quantity')
        if quantity is None:
            raise ValueError("Missing quantity")
        try:
            parsed['quantity'] = int(quantity)
            if parsed['quantity'] <= 0:
                raise ValueError("Quantity must be positive")
        except (ValueError, TypeError):
            raise ValueError(f"Invalid quantity: {quantity}")
        
        # Extract optional price
        price = data.get('price')
        if price is not None:
            try:
                parsed['price'] = float(price)
            except (ValueError, TypeError):
                raise ValueError(f"Invalid price: {price}")
        
        # Extract optional message
        parsed['message'] = str(data.get('message', ''))
        
        # Extract optional timestamp
        timestamp = data.get('timestamp')
        if timestamp:
            try:
                # Validate timestamp format
                datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                parsed['timestamp'] = timestamp
            except ValueError:
                # Use current timestamp if invalid
                pass
        
        return parsed