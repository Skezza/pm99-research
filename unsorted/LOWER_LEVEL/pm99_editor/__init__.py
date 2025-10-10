"""PM99 Database Editor - Reverse-engineered editor for Premier Manager 99.

This package provides tools to read, modify, and write PM99 FDI database files.
Based on reverse engineering of MANAGPRE.EXE, DBASEPRE.EXE from the original game.

Example usage:
    from pm99_editor import FDIFile
    
    # Load database
    fdi = FDIFile('DBDAT/JUG98030.FDI')
    fdi.load()
    
    # Find and rename a player
    player = fdi.find_by_id(123)
    player.given_name = "Cristiano"
    player.surname = "Ronaldo"
    
    # Save changes
    fdi.save(backup=True)
"""

__version__ = '0.1.0'
__author__ = 'Reverse Engineering Project'

from .models import PlayerRecord, FDIHeader, DirectoryEntry
from .io import FDIFile
from .xor import decode_entry, encode_entry, read_string, write_string

__all__ = [
    'PlayerRecord',
    'FDIHeader',
    'DirectoryEntry',
    'FDIFile',
    'decode_entry',
    'encode_entry',
    'read_string',
    'write_string',
]