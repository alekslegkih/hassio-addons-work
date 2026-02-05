#!/usr/bin/env python3
"""
Home Assistant notifier for sending notifications via Supervisor API.
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
    notification_id: Optional[str] = None  # For persistent notifications
    level: str = "info"  # info, warning, error

class HANotifier:
    """
    Client for sending notifications to Home Assistant.
    
    Uses Supervisor REST API with authentication token.
    """
    
    # Default notification service
    DEFAULT_SERVICE = "persistent_notification"
    
    # Service mappings for different notification types
    SERVICE_MAP = {
        "persistent_notification": "persistent_notification",
        "notify": "notify",
        "mobile_app": "notify.mobile_app",
        "telegram": "notify.telegram",
    }
    
    def __init__(self, service: Optional[str] = None):
        """
        Initialize notifier.
        
        Args:
            service: HA service to use for notifications
                   (e.g., 'persistent_notification', 'notify.mobile_app')
        """
        self.service = service or self.DEFAULT_SERVICE
        self.token = os.environ.get("SUPERVISOR_TOKEN")
        self.base_url = "http://supervisor"
        
        if not self.token:
            logger.warning("SUPERVISOR_TOKEN not found. Notifications will be logged only.")
    
    def send_notification(
        self,
        title: str,
        message: str,
        service: Optional[str] = None,
        level: str = "info",
        notification_id: Optional[str] = None
    ) -> bool:
        """
        Send notification to Home Assistant.
        
        Args:
            title: Notification title
            message: Notification message
            service: Override default service
            level: Notification level (info, warning, error)
            notification_id: ID for persistent notifications
            
        Returns:
            True if notification was sent successfully
        """
        service_to_use = service or self.service
        
        # Create notification object
        notification = Notification(
            title=title,
            message=message,
            level=level,
            notification_id=notification_id
        )
        
        # Log notification
        self._log_notification(notification, service_to_use)
        
        # Try to send via HA API if token is available
        if self.token:
            return self._send_via_api(notification, service_to_use)
        else:
            logger.warning("Cannot send notification: No SUPERVISOR_TOKEN available")
            return False
    
    def send_info_notification(self, title: str, message: str) -> bool:
        """Send info notification"""
        return self.send_notification(title, message, level="info")
    
    def send_warning_notification(self, title: str, message: str) -> bool:
        """Send warning notification"""
        return self.send_notification(title, message, level="warning")
    
    def send_error_notification(self, title: str, message: str) -> bool:
        """Send error notification"""
        return self.send_notification(title, message, level="error")
    
    def send_persistent_notification(
        self,
        title: str,
        message: str,
        notification_id: Optional[str] = None
    ) -> bool:
        """
        Send persistent notification (stays until dismissed).
        
        Args:
            title: Notification title
            message: Notification message
            notification_id: Unique ID for the notification
                           (if not provided, will be generated from title)
        """
        if not notification_id:
            # Generate ID from title
            import re
            notification_id = re.sub(r'[^a-zA-Z0-9_]', '_', title.lower())
            notification_id = f"backup_sync_{notification_id}"
        
        return self.send_notification(
            title=title,
            message=message,
            service="persistent_notification",
            notification_id=notification_id
        )
    
    def clear_persistent_notification(self, notification_id: str) -> bool:
        """
        Clear a persistent notification.
        
        Args:
            notification_id: ID of notification to clear
            
        Returns:
            True if cleared successfully
        """
        if not self.token:
            logger.warning("Cannot clear notification: No SUPERVISOR_TOKEN")
            return False
        
        try:
            # For persistent_notification service, we need to call dismiss
            url = f"{self.base_url}/core/api/services/persistent_notification/dismiss"
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            data = {
                "notification_id": notification_id
            }
            
            logger.debug(f"Clearing notification {notification_id}")
            response = requests.post(url, json=data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"Cleared persistent notification: {notification_id}")
                return True
            else:
                logger.error(f"Failed to clear notification {notification_id}: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error clearing notification {notification_id}: {e}")
            return False
    
    def _send_via_api(self, notification: Notification, service: str) -> bool:
        """Send notification via Supervisor API"""
        try:
            # Parse service into domain and service name
            if "." in service:
                domain, service_name = service.split(".", 1)
            else:
                domain = service
                service_name = "create" if service == "persistent_notification" else service
            
            # Build URL
            url = f"{self.base_url}/core/api/services/{domain}/{service_name}"
            
            # Prepare headers
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            # Prepare data based on service type
            data = self._prepare_notification_data(notification, service)
            
            # Send request
            logger.debug(f"Sending notification via {service}: {notification.title}")
            response = requests.post(url, json=data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"Notification sent: {notification.title}")
                return True
            else:
                logger.error(
                    f"Failed to send notification: {response.status_code} - {response.text}"
                )
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error sending notification: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return False
    
    def _prepare_notification_data(
        self,
        notification: Notification,
        service: str
    ) -> Dict[str, Any]:
        """Prepare notification data for different service types"""
        
        if service == "persistent_notification":
            # Persistent notification data structure
            data = {
                "title": notification.title,
                "message": notification.message,
            }
            
            if notification.notification_id:
                data["notification_id"] = notification.notification_id
            
            return data
        
        else:
            # Generic notify service structure
            data = {
                "title": notification.title,
                "message": notification.message,
            }
            
            # Add level if supported
            if hasattr(notification, 'level'):
                data["data"] = {"importance": notification.level}
            
            return data
    
    def _log_notification(self, notification: Notification, service: str) -> None:
        """Log notification to console"""
        level_map = {
            "info": "INFO",
            "warning": "WARNING",
            "error": "ERROR"
        }
        
        level_str = level_map.get(notification.level, "INFO")
        
        logger.info(f"Notification [{level_str}] via {service}: {notification.title}")
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
    
    def get_available_services(self) -> list:
        """
        Get list of available notification services.
        Requires HA API access.
        
        Returns:
            List of service names
        """
        if not self.token:
            return []
        
        try:
            url = f"{self.base_url}/core/api/services"
            headers = {"Authorization": f"Bearer {self.token}"}
            
            response = requests.get(url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                services = response.json()
                # Filter notification services
                notify_services = []
                for domain, service_list in services.items():
                    if "notify" in domain.lower():
                        for service in service_list:
                            notify_services.append(f"{domain}.{service}")
                return notify_services
            else:
                return []
                
        except Exception:
            return []