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


    
class Singleton2(object):
    _instance = None
    def __new__(class_, *args, **kwargs):
        if not isinstance(class_._instance, class_):
            class_._instance = object.__new__(class_, *args, **kwargs)
        return class_._instance    
    
'''
class ClassA(Singleton2,app_manager.RyuApp):
    #__metaclass__ = Singleton
    
    def __init__(self, *args, **kwargs):
        
        super(ClassA, self).__init__(*args, **kwargs)
        self.name = "classA"
        self.num = 5
        print "istanziato"
        
       
if __name__ == '__main__':
    
    a = ClassA()
    b = ClassA()
    b.num = 6
    print a is b
    print a.num
'''
    
    
    
    