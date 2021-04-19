import sys
from kdl import *
import tatsu

tvGrammar = r'''
@@whitespace :: /\s+/

toplevel_type = type $;
toplevel_value = value $;

type = array:array_type | generic:generic_type | named:identifier;
array_type = base:type '[' rank:value ']';
generic_type = base:type '<' generics:'|'.{ type }+ '>';

value = comparison | binary_op | slice | index | member_access | call | number | variable;
comparison = left:value comparison:('<' | '<=' | '==' | '!=' | '>=' | '>') right:value;
binary_op = left:value binary_op:('+' | '-' | '*' | '/') right:value; # TODO: Add order of operations!
slice = slice_middle:slice_middle | slice_left:slice_left | slice_right:slice_right;
slice_right = start:value '...';
slice_left = '...' end:value;
slice_middle = start:value '...' end:value;
member_access = base:value '.' member:identifier;
call = func:identifier '(' arg:value ')';
index = base:value '[' index:value ']';
variable = variable:identifier;
identifier = !digit @+:first_identifier_char {@+:rest_identifier_char};
number = hex | octal | binary | decimal;

decimal = decimal:/[+\-]?[0-9][0-9_]*/;
hex = hex:/[+\-]?0x[0-9a-fA-F][0-9a-fA-F_]*/;
octal = octal:/[+\-]?0o[0-7][0-7_]*/;
binary = binary:/[+\-]?0b[01][01_]*/;

digit = /[0-9]/;
first_identifier_char = !linespace !/[\\<>{}();\[\]=,"\.+\-*\/]/ /./;
rest_identifier_char = !linespace !/[\\\[\]()<>;=,"\.+\-*\/]/ /./;
linespace = newline | ws | $;
newline = /(\r\n|[\r\n\u0085\u000C\u2028\u2029])/;
ws = /([\t \u00A0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200A\u202F\u205F\u3000]|\uFFEF)+/;
'''

model = tatsu.compile(tvGrammar, name='TvGrammar')

def parseValueAst(ast):
	if 'variable' in ast:
		return ('variable', u''.join(ast['variable']))
	elif 'decimal' in ast:
		return ('value', int(ast['decimal'].replace('_', '')))
	elif 'index' in ast:
		return ('subscript', parseValueAst(ast['base']), parseValueAst(ast['index']))
	elif 'slice_right' in ast:
		return ('slice', parseValueAst(ast['slice_right']['start']), None)
	elif 'slice_left' in ast:
		return ('slice', None, parseValueAst(ast['slice_left']['end']))
	elif 'member' in ast:
		return ('property', parseValueAst(ast['base']), u''.join(ast['member']))
	elif 'comparison' in ast:
		return ('compare', parseValueAst(ast['left']), ast['comparison'], parseValueAst(ast['right']))
	elif 'binary_op' in ast:
		return ('binary_op', parseValueAst(ast['left']), ast['binary_op'], parseValueAst(ast['right']))
	elif 'func' in ast:
		return ('call', u''.join(ast['func']), parseValueAst(ast['arg']))
	print ast
	assert False

vsCache = {}
def parseValueString(value):
	if value in vsCache:
		return vsCache[value]
	ast = model.parse(value, start='toplevel_value')
	tree = parseValueAst(ast)
	vsCache[value] = tree
	return tree

tsCache = {}
def parseTypeString(type):
	if type in tsCache:
		return tsCache[type]
	ast = model.parse(type, start='toplevel_type')
	def recur(ast):
		if 'named' in ast:
			return ('named', u''.join(ast['named']))
		elif 'array' in ast:
			return ('array', recur(ast['array']['base']), parseValueAst(ast['array']['rank']))
		elif 'generic' in ast:
			return ('generic', recur(ast['generic']['base']), map(recur, ast['generic']['generics']))
		else:
			print ast
			assert False
	tree = recur(ast)
	tsCache[type] = tree
	return tree

class Type(object):
	def __init__(self, basename, generics):
		self.basename = basename
		self.generics = generics
		self.name = '%s<%s>' % (basename, u'|'.join(generics)) if generics else basename

	def specialize(self, genericSubs):
		assert len(genericSubs) == len(self.generics)
		return SpecializedType(self, genericSubs)

	def __repr__(self):
		return self.name

	def equivalent(self, other):
		raise Exception('Cannot check equivalence of %r' % self.__class__)

class Struct(Type):
	def __init__(self, basename, generics, body):
		Type.__init__(self, basename, generics)
		self.body = body

	def equivalent(self, other):
		if not isinstance(other, Struct):
			return False
		return self.basename == other.basename

class SpecializedType(Type):
	def __init__(self, base, genericSubs):
		Type.__init__(self, base.basename, [x.name for x in genericSubs])
		self.base = base
		self.genericSubs = genericSubs

	def equivalent(self, other):
		if not isinstance(other, SpecializedType):
			return False
		if not self.base.equivalent(other.base):
			return False
		return all(a.equivalent(b) for a, b in zip(self.genericSubs, other.genericSubs))

class Typedef(Type):
	def __init__(self, basename, generics, otype):
		Type.__init__(self, basename, generics)
		self.otype = otype

class Macro(object):
	def __init__(self, name, argnames, body):
		self.name = name
		self.argnames = argnames
		self.body = body

class FluffySpec(object):
	def __init__(self, spec):
		doc = Document(spec)
		self.typedefs = {}
		self.fileMatchers = {}

		for node in doc:
			if node.name == 'typedef':
				assert isinstance(node[0], Symbol) and isinstance(node[1], Symbol)
				basename, generics = self.parseTypedefName(node[0].value)
				self.typedefs[node[0].value] = Typedef(basename, generics, node[1].value)
			elif node.name == 'match-extension':
				assert isinstance(node[1], Symbol)
				self.fileMatchers[('extension', node[0].lower())] = node[1].value
			elif node.name == 'struct':
				assert isinstance(node[0], Symbol)
				basename, generics = self.parseTypedefName(node[0].value)
				self.typedefs[basename] = Struct(basename, generics, node.children)
			else:
				print 'Unsupported top-level node:', node

	def parseTypedefName(self, name):
		if '<' in name:
			basename, generics = name.split('<', 1)
			assert '<' not in generics and '>' not in generics[:-1] and generics[-1] == '>'
			return basename, generics[:-1].split('|')
		else:
			return name, None

def main(sfn):
	fluffy = FluffySpec(file(sfn, 'r'))

if __name__=='__main__':
	main(*sys.argv[1:])
