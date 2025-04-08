"""
AWS Cost Explorer integration for cost estimation.
"""
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
import backoff

from botocore.exceptions import ClientError

from vox_biblios.aws.aws_client import get_ce_client
from vox_biblios.utils.logging import get_logger
from vox_biblios.exceptions import CostEstimationError

logger = get_logger(__name__)


class CostEstimationService:
    """Service for AWS cost estimation."""
    
    def __init__(self):
        """Initialize the cost estimation service."""
        self.client = get_ce_client()
        logger.debug("Initialized CostEstimationService")
    
    def get_monthly_cost(self, 
                         days: int = 30, 
                         end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Get estimated AWS cost for a specified period.
        
        Args:
            days: Number of days to look back
            end_date: End date (defaults to today)
            
        Returns:
            Dictionary with cost information
            
        Raises:
            CostEstimationError: If the cost estimation fails
        """
        logger.info(f"Getting cost estimate for the last {days} days")
        
        try:
            # Calculate time period
            end_date = end_date or datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            # Format dates
            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')
            
            logger.debug(f"Cost date range: {start_str} to {end_str}")
            
            # Get cost data
            response = self._get_cost_with_retry(start_str, end_str)
            
            # Extract cost
            cost_value = float(response['ResultsByTime'][0]['Total']['UnblendedCost']['Amount'])
            currency = response['ResultsByTime'][0]['Total']['UnblendedCost']['Unit']
            
            result = {
                'cost': cost_value,
                'currency': currency,
                'start_date': start_str,
                'end_date': end_str,
                'days': days,
                'formatted': f"${cost_value:.2f} {currency}"
            }
            
            logger.info(f"Estimated cost: {result['formatted']}")
            return result
            
        except Exception as e:
            error_msg = f"Failed to estimate AWS cost: {str(e)}"
            logger.error(error_msg)
            raise CostEstimationError(error_msg) from e
    
    def get_service_costs(self, 
                          days: int = 30, 
                          end_date: Optional[datetime] = None) -> Dict[str, float]:
        """
        Get costs broken down by AWS service.
        
        Args:
            days: Number of days to look back
            end_date: End date (defaults to today)
            
        Returns:
            Dictionary mapping service names to costs
            
        Raises:
            CostEstimationError: If the service cost estimation fails
        """
        logger.info(f"Getting service costs for the last {days} days")
        
        try:
            # Calculate time period
            end_date = end_date or datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            # Format dates
            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')
            
            # Get cost by service
            response = self._get_cost_by_service_with_retry(start_str, end_str)
            
            # Extract costs by service
            services = {}
            for group in response.get('ResultsByTime', [{}])[0].get('Groups', []):
                service_name = group.get('Keys', ['Unknown'])[0]
                cost_value = float(group.get('Metrics', {}).get('UnblendedCost', {}).get('Amount', 0))
                services[service_name] = cost_value
            
            logger.info(f"Retrieved costs for {len(services)} services")
            return services
            
        except Exception as e:
            error_msg = f"Failed to get service costs: {str(e)}"
            logger.error(error_msg)
            raise CostEstimationError(error_msg) from e
    
    def get_cost_forecast(self, days_forward: int = 30) -> Dict[str, Any]:
        """
        Get cost forecast for the future period.
        
        Args:
            days_forward: Number of days to forecast
            
        Returns:
            Dictionary with forecast information
            
        Raises:
            CostEstimationError: If the forecast fails
        """
        logger.info(f"Getting cost forecast for the next {days_forward} days")
        
        try:
            # Calculate time period
            start_date = datetime.utcnow()
            end_date = start_date + timedelta(days=days_forward)
            
            # Format dates
            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')
            
            # Get forecast
            response = self._get_forecast_with_retry(start_str, end_str)
            
            # Extract forecast
            forecast = {
                'mean': float(response['Total']['Amount']),
                'currency': response['Total']['Unit'],
                'start_date': start_str,
                'end_date': end_str,
                'days': days_forward,
                'formatted': f"${float(response['Total']['Amount']):.2f} {response['Total']['Unit']}"
            }
            
            logger.info(f"Cost forecast: {forecast['formatted']}")
            return forecast
            
        except Exception as e:
            error_msg = f"Failed to get cost forecast: {str(e)}"
            logger.error(error_msg)
            raise CostEstimationError(error_msg) from e
    
    def format_cost_summary(self) -> str:
        """
        Create a formatted cost summary string.
        
        Returns:
            Formatted cost summary
        """
        try:
            # Get monthly cost
            monthly = self.get_monthly_cost()
            
            # Get service breakdown
            services = self.get_service_costs()
            
            # Format the summary
            summary = []
            summary.append(f"AWS Cost Summary (Last {monthly['days']} days)")
            summary.append(f"Total: {monthly['formatted']}")
            summary.append("")
            summary.append("Service Breakdown:")
            
            # Add top services by cost
            sorted_services = sorted(services.items(), key=lambda x: x[1], reverse=True)
            for service, cost in sorted_services[:5]:  # Top 5 services
                summary.append(f"- {service}: ${cost:.2f}")
            
            return "\n".join(summary)
            
        except Exception as e:
            logger.error(f"Failed to create cost summary: {str(e)}")
            return f"Estimated AWS cost: (unable to fetch)"
    
    @backoff.on_exception(
        backoff.expo,
        ClientError,
        max_tries=3,
        jitter=backoff.full_jitter
    )
    def _get_cost_with_retry(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        Get cost data with retry mechanism.
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            AWS Cost Explorer response
        """
        return self.client.get_cost_and_usage(
            TimePeriod={
                'Start': start_date,
                'End': end_date
            },
            Granularity='MONTHLY',
            Metrics=['UnblendedCost']
        )
    
    @backoff.on_exception(
        backoff.expo,
        ClientError,
        max_tries=3,
        jitter=backoff.full_jitter
    )
    def _get_cost_by_service_with_retry(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        Get cost by service with retry mechanism.
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            AWS Cost Explorer response
        """
        return self.client.get_cost_and_usage(
            TimePeriod={
                'Start': start_date,
                'End': end_date
            },
            Granularity='MONTHLY',
            Metrics=['UnblendedCost'],
            GroupBy=[
                {
                    'Type': 'DIMENSION',
                    'Key': 'SERVICE'
                }
            ]
        )
    
    @backoff.on_exception(
        backoff.expo,
        ClientError,
        max_tries=3,
        jitter=backoff.full_jitter
    )
    def _get_forecast_with_retry(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        Get cost forecast with retry mechanism.
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            AWS Cost Explorer forecast response
        """
        return self.client.get_cost_forecast(
            TimePeriod={
                'Start': start_date,
                'End': end_date
            },
            Metric='UNBLENDED_COST',
            Granularity='MONTHLY'
        )