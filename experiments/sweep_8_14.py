"""Hold-duration sweep, days 8-14 (7d included as the reference anchor).
See hold_duration.py for methodology. Pre-registered question: where does
the post-absorption drift plateau? Keep 7d unless the answer is unambiguous.
"""
from hold_duration import main

if __name__ == "__main__":
    main([7, 8, 9, 10, 11, 12, 13, 14], "7-14d")
