import email.utils

def normalize_email_address(raw_str: str) -> str:
    """
    Extracts the clean 'user@domain.com' from a Gmail-style header string.
    Example: 'Anshu Nandi <anshu.nandi@gmail.com>' -> 'anshu.nandi@gmail.com'
    Handles varying formats, display names, and casing safely.
    """
    if not raw_str:
        return ""
    
    # email.utils.parseaddr is the standard library way to handle 'Name <email>'
    name, addr = email.utils.parseaddr(raw_str)
    
    # If parseaddr fails or returns empty, fallback to simple strip/lower
    clean_addr = (addr or raw_str).strip().lower()
    
    return clean_addr
