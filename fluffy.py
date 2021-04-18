import sys
from generator import *
from backends import PythonBackend

def main(sfn):
	from backends import PythonBackend
	Generator(file(sfn, 'r'), PythonBackend(file('testoutput.py', 'w')))

if __name__=='__main__':
	main(*sys.argv[1:])
