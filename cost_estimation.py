import boto3
from datetime import datetime, timedelta
from config import AWS_ACCESS_KEY, AWS_SECRET_KEY

def estimate_monthly_cost():
    try:
        client = boto3.client('ce',
                              aws_access_key_id=AWS_ACCESS_KEY,
                              aws_secret_access_key=AWS_SECRET_KEY,
                              region_name='us-east-1')

        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=30)

        response = client.get_cost_and_usage(
            TimePeriod={
                'Start': start_date.isoformat(),
                'End': end_date.isoformat()
            },
            Granularity='MONTHLY',
            Metrics=['UnblendedCost']
        )

        cost = float(response['ResultsByTime'][0]['Total']['UnblendedCost']['Amount'])
        return f"Estimated AWS cost for the last 30 days: ${cost:.2f}"
    except Exception as e:
        return f"Unable to estimate AWS cost: {str(e)}"