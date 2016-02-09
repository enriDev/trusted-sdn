'''
Created on Feb 7, 2016

@author: root
'''

from ryu.base import app_manager
from _pyio import __metaclass__


class Singleton(type):
    """Singleton class to which derive from.
    Metaclass implementation
    """
    _instances = {}
    
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


    

    
    
    
    