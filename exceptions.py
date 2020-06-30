class BananaCrime(Exception):
    """Represents a "more precise" input error.
    
    Args:
        crime (str): A description of what was wrong.
    """
    def __init__(self, crime):
        self.crime = crime
