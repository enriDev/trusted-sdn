'''
Created on Feb 1, 2016

Define the security class

@author: root
'''


""" 
Security class from the highest to lowest:
strategit > sensitive > confidential > public 

Example of usage:

    SecurityClass.CONFIDENTIAL
"""

security_class_list = ['STRATEGIC', 'SENSITIVE', 'CONFIDENTIAL', 'PUBLIC']

#utility function that implement enum
def enum(*args):
    enum_list = zip(args, range(len(args)))
    enums = dict(enum_list)
    return type('Enum', (), enums)

#SecurityClass = enum(security_class_list)
SecurityClass = dict( [('CONFIDENTIAL',0), ('PUBLIC', 2)] )