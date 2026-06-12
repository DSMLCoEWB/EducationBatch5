import dns.resolver
import logging

logger = logging.getLogger("dns_utils")

def detect_mail_provider(email: str) -> str:
    """
    Dynamically queries DNS MX records to determine the mail provider for a given email address.
    Returns: "google", "microsoft", or "unknown"
    """
    try:
        if '@' not in email:
            return "unknown"
            
        domain = email.split('@')[-1]
        
        # Query MX records
        answers = dns.resolver.resolve(domain, 'MX')
        
        for rdata in answers:
            exchange = str(rdata.exchange).lower()
            
            # Check for Google Workspace / Gmail
            if 'google.com' in exchange or 'googlemail.com' in exchange:
                return "google"
                
            # Check for Microsoft 365 / Outlook / Exchange Online
            if 'outlook.com' in exchange or 'protection.outlook.com' in exchange or 'hotmail.com' in exchange:
                return "microsoft"
                
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.exception.Timeout, Exception) as e:
        logger.warning(f"Failed to resolve MX records for {email}: {e}")
        
    return "unknown"
