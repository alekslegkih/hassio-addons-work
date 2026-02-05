#!/usr/bin/env python3
"""
Notification sender for sending messages via Home Assistant notify services.
Uses SUPERVISOR_TOKEN for authentication.
"""

import os
import json
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

@dataclass
class Notification:
    """Notification data structure"""
    title: str
    message: str
    level: str = "info"  # info, warning, error

class NotifySender:
    """
    Client for sending notifications via Home Assistant notify services.
    
    Uses Supervisor REST API with authentication token.
    """
    
    def __init__(self, notify_service: str = "notification_channel"):
        """
        Initialize notification sender.
        
        Args:
            notify_service: Name of the notify service to use
                          (e.g., 'notification_channel', 'mobile_app', 'telegram')
                          Will be used as 'notify.{notify_service}'
        """
        self.notify_service = notify_service
        self.token = os.environ.get("SUPERVISOR_TOKEN")
        self.base_url = "http://supervisor"
        
        if not self.token:
            logger.warning("SUPERVISOR_TOKEN not found. Notifications will be logged only.")
        
        # Full service name
        self.full_service = f"notify.{self.notify_service}"
        logger.debug(f"NotifySender initialized with service: {self.full_service}")
    
    def send_notification(
        self,
        title: str,
        message: str,
        level: str = "info"
    ) -> bool:
        """
        Send notification via notify service.
        
        Args:
            title: Notification title
            message: Notification message
            level: Notification level (info, warning, error)
            
        Returns:
            True if notification was sent successfully
        """
        # Create notification object
        notification = Notification(
            title=title,
            message=message,
            level=level
        )
        
        # Log notification
        self._log_notification(notification)
        
        # Try to send via HA API if token is available
        if self.token:
            return self._send_via_api(notification)
        else:
            logger.warning("Cannot send notification: No SUPERVISOR_TOKEN available")
            return False
    
    def send_info(self, title: str, message: str) -> bool:
        """Send info notification"""
        return self.send_notification(title, message, level="info")
    
    def send_warning(self, title: str, message: str) -> bool:
        """Send warning notification"""
        return self.send_notification(title, message, level="warning")
    
    def send_error(self, title: str, message: str) -> bool:
        """Send error notification"""
        return self.send_notification(title, message, level="error")
    
    def _send_via_api(self, notification: Notification) -> bool:
        """Send notification via Supervisor API"""
        try:
            # Build URL - format: /core/api/services/notify/{service_name}
            url = f"{self.base_url}/core/api/services/notify/{self.notify_service}"
            
            # Prepare headers
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            # Prepare data
            data = {
                "title": notification.title,
                "message": notification.message,
                "data": {"importance": notification.level}
            }
            
            # Send request
            logger.debug(f"Sending notification via {self.full_service}: {notification.title}")
            response = requests.post(url, json=data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"Notification sent via {self.full_service}: {notification.title}")
                return True
            else:
                logger.error(
                    f"Failed to send notification via {self.full_service}: "
                    f"{response.status_code} - {response.text}"
                )
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error sending notification: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return False
    
    def _log_notification(self, notification: Notification) -> None:
        """Log notification to console"""
        level_map = {
            "info": "INFO",
            "warning": "WARNING",
            "error": "ERROR"
        }
        
        level_str = level_map.get(notification.level, "INFO")
        
        logger.info(f"Notification [{level_str}] via {self.full_service}: {notification.title}")
        if notification.message:
            # Log message in multiple lines if it's long
            lines = notification.message.split('\n')
            for line in lines[:3]:  # Log first 3 lines
                if line.strip():
                    logger.info(f"  {line}")
            if len(lines) > 3:
                logger.info(f"  ... and {len(lines) - 3} more lines")
    
    def test_connection(self) -> bool:
        """
        Test connection to Supervisor API.
        
        Returns:
            True if connection successful
        """
        if not self.token:
            logger.warning("Cannot test connection: No SUPERVISOR_TOKEN")
            return False
        
        try:
            url = f"{self.base_url}/core/api/"
            headers = {"Authorization": f"Bearer {self.token}"}
            
            response = requests.get(url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                logger.info("Successfully connected to Supervisor API")
                return True
            else:
                logger.error(f"API connection failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False