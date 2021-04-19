from generator import *
from backend import banner, Backend
import keyword
import struct as S

headerCode = r'''
from __future__ import print_function
import struct as __struct__
def _arrayUnpack(fp, fmt, elemSize, rank):
	return list(__struct__.unpack('<' + fmt*rank, fp.read(elemSize*rank)))
def _prepr(expr, indent=1):
	if isinstance(expr, list) or isinstance(expr, tuple):
		cc = '[%s]' if isinstance(expr, list) else '(%s)'
		elems = [_prepr(x, 2) for x in expr]
		js = u',\n' if any('\n' in x for x in elems) else u', '
		if len(elems) == 1 and cc[0] == '(':
			elems.append('')
		return cc % js.join(elems).lstrip()
	expr = repr(expr)
	if '\n' in expr:
		ti = '\t' * indent
		expr = expr.split('\n')
		if indent == 1:
			return u'\n'.join([expr[0]] + [ti + x for x in expr[1:]])
		else:
			return u'\n'.join(ti + x for x in expr)
	return expr
def _divHelper(a, b):
	if (isinstance(a, int) or isinstance(a, long)) and (isinstance(b, int) or isinstance(b, long)):
		return a // b
	return a / b
'''.strip()

def sanitize(name):
	if name in keyword.kwlist or name[0] in '0123456789':
		return sanitize('_' + name)
	if '<' in name or '>' in name:
		return sanitize(name.replace('<', '_').replace('>', ''))
	return name

def genExpr(tree, struct):
	def sub(tree):
		if tree is None:
			return 'None'
		if tree[0] == 'compare':
			return '(%s) %s (%s)' % (sub(tree[1]), tree[2], sub(tree[3]))
		elif tree[0] == 'binary_op':
			if tree[2] == '/':
				return '_divHelper(%s, %s)' % (sub(tree[1]), sub(tree[3]))
			else:
				return '(%s) %s (%s)' % (sub(tree[1]), tree[2], sub(tree[3]))
		elif tree[0] == 'variable':
			if tree[1] in struct.fields:
				return 'self.%s' % sanitize(tree[1])
			else:
				return sanitize(tree[1])
		elif tree[0] == 'value':
			return repr(tree[1])
		elif tree[0] == 'property':
			return '(%s).%s' % (sub(tree[1]), sanitize(tree[2]))
		elif tree[0] == 'cast-to':
			assert isinstance(tree[1], CStringType) # TODO: Add more casts
			return "''.join(map(chr, %s)).split('\\0', 1)[0]" % sub(tree[2]) # TODO: Optimize
		elif tree[0] == 'subscript':
			return '%s[%s]' % (sub(tree[1]), sub(tree[2]))
		elif tree[0] == 'slice':
			return '%s:%s' % (sub(tree[1]), sub(tree[2]))
		else:
			print tree
			assert False
	return sub(tree)

ifc = {
	(8, False) : 'B', 
	(16, False) : 'H', 
	(32, False) : 'I', 
	(64, False) : 'Q', 
	(8, True) : 'b', 
	(16, True) : 'h', 
	(32, True) : 'i', 
	(64, True) : 'q', 
}
ffc = {
	32 : 'f', 
	64 : 'd', 
}

class PythonBackend(Backend):
	LANGUAGE = 'python'
	EXTENSION = 'py'

	def generate(self, spec):
		self.spec = spec
		for line in banner:
			self.writeLine('#', line)
		self.writeLine('#')
		self.writeLine('# DO NOT EDIT')
		self.writeLine('# Generated automatically by Fluffy')

		self.writeLine(headerCode)

		for name, struct in spec.structs.items():
			self.writeLine()
			self.writeLine('class %s(object):' % sanitize(name))
			self.indent()
			self.writeLine('def __init__(self%s):' % (', ' + u', '.join(sanitize(fn) + '=None' for fn in struct.fields) if struct.fields else ''))
			self.indent()
			if struct.fields:
				for fn, fts in struct.fields.items():
					self.writeLine('self.%s = %s # %s' % (sanitize(fn), sanitize(fn), u' or '.join(map(repr, fts))))
			else:
				self.writeLine('pass')
			self.dedent()
			self.writeLine()

			self.writeLine('def __unpack__(self, fp%s):' % (', ' + u', '.join(map(sanitize, sorted(struct.dependencies.keys()))) if struct.dependencies else ''))
			self.indent()
			def recur(steps):
				for step in steps:
					if step[0] == 'magic':
						self.writeLine('assert fp.read(%i) == %r' % (len(step[1]), step[1]))
					elif step[0] == 'unsupported':
						self.writeLine('assert False')
					elif step[0] == 'unpack':
						self.writeLine('%s = %s' % (u', '.join('self.' + sanitize(var) for var in step[2]), self.genUnpack(step[1], struct, len(step[2]))))
					elif step[0] == 'assign':
						self.writeLine('self.%s = %s' % (sanitize(step[1]), genExpr(step[3], struct)))
					elif step[0] == 'mark_position':
						self.writeLine('self.%s = fp.tell()' % sanitize(step[1]))
					elif step[0] == 'seek_abs_scoped':
						oldPos = self.tempvar()
						self.writeLine('%s = fp.tell()' % oldPos)
						self.writeLine('fp.seek(%s, 0)' % genExpr(step[1], struct))
						recur(step[2])
						self.writeLine('fp.seek(%s, 0)' % oldPos)
					elif step[0] == 'seek_abs':
						self.writeLine('fp.seek(%s, 0)' % genExpr(step[1], struct))
					elif step[0] == 'match':
						comp = '__matchee__'
						if len(step[2]) == 0:
							continue
						elif len(step[2]) == 1 and step[2][0][0] is None:
							recur(step[2][0][1])
						else:
							self.writeLine('%s = %s' % (comp, genExpr(step[1], struct)))
							first = True
							for case, body in step[2]:
								if case is not None:
									self.writeLine('%sif %s == %s:' % ('' if first else 'el', comp, genExpr(case, struct)))
								else:
									self.writeLine('else:')
								self.indent()
								recur(body)
								self.dedent()
								first = False
					elif step[0] == 'if':
						self.writeLine('if %s:' % genExpr(step[1], struct))
						self.indent()
						if not step[2]:
							self.writeLine('pass')
						else:
							recur(step[2])
						self.dedent()
						if step[3]:
							self.writeLine('else:')
							self.indent()
							recur(step[3])
							self.dedent()
					else:
						print step
						assert False
			recur(struct.unpackSteps)
			self.writeLine('return self')
			self.dedent()

			self.writeLine()
			self.writeLine('def __repr__(self):')
			self.indent()
			toPrint = [sanitize(fn) for fn in struct.fields.keys() if not fn.startswith('_') and fn[0].upper() == fn[0]]
			if len(toPrint) == 0:
				self.writeLine('return \'%s()\'' % sanitize(name))
			else:
				self.writeLine('ret = \'%s(\\n\'' % sanitize(name))
				for fn in toPrint:
					self.writeLine('if self.%s is not None:' % fn)
					self.indent()
					self.writeLine('ret += \'\\t%s=%%s,\\n\' %% _prepr(self.%s)' % (fn, fn))
					self.dedent()
				self.writeLine('return ret + \')\'')
			self.dedent()
			self.dedent()

		self.writeLine()
		self.writeLine('__all__ = %r' % map(sanitize, spec.structs.keys()))
		if not any(not struct.dependencies for struct in spec.structs.values()):
			return
		extMap = {ent[1] : type for ent, type in spec.fileMatchers.items() if ent[0] == 'extension'}
		self.writeLine()
		self.writeLine('if __name__==\'__main__\':')
		self.indent()
		self.writeLine('import sys')
		self.writeLine('if len(sys.argv) <= %i:' % (1 if len(extMap) else 2))
		self.indent()
		self.writeLine('print(\'Usage: %%s <file_to_parse> %sstarting_struct%s\' %% sys.argv[0], file=sys.stderr)' % (('[', ']') if len(extMap) else ('<', '>')))
		self.writeLine('sys.exit(1)')
		self.dedent()
		self.writeLine('elif len(sys.argv) > 2:')
		self.indent()
		first = True
		for name, struct in spec.structs.items():
			if struct.dependencies:
				continue
			self.writeLine('%sif sys.argv[2] == %r:' % ('' if first else 'el', sanitize(name)))
			first = False
			self.indent()
			self.writeLine('start = %s' % sanitize(name))
			self.dedent()
		self.writeLine('else:')
		self.indent()
		self.writeLine('print(\'Invalid starting struct specified\', file=sys.stderr)')
		self.writeLine('sys.exit(1)')
		self.dedent()
		self.dedent()
		if extMap:
			self.writeLine('else:')
			self.indent()
			self.writeLine('ext = sys.argv[1].rsplit(\'.\', 1)[-1].lower()')
			first = True
			for ext, type in extMap.items():
				self.writeLine('%sif ext == %r:' % ('' if first else 'el', ext))
				first = False
				self.indent()
				self.writeLine('start = %s' % sanitize(type))
				self.dedent()
			self.writeLine('else:')
			self.indent()
			self.writeLine('print(\'Could not determine starting struct from file extension\', file=sys.stderr)')
			self.writeLine('sys.exit(1)')
			self.dedent()
			self.dedent()
		self.writeLine('print(start().__unpack__(open(sys.argv[1], \'rb\')))')

	def genUnpack(self, type, struct, count):
		mult = lambda x: x if count == 1 else u', '.join([x] * count)
		if isinstance(type, IntType) or isinstance(type, FloatType):
			if isinstance(type, IntType):
				fc = ifc[(type.bits, type.signed)]
			else:
				fc = ffc[type.bits]
			fmt = '<' + fc * count
			cmd = '__struct__.unpack(%r, fp.read(%i))' % (fmt, S.calcsize(fmt))
			return cmd + '[0]' if count == 1 else cmd
		elif isinstance(type, ArrayType):
			bt = type.base
			while isinstance(bt, Typedef):
				bt = bt.otype
			if not isinstance(bt, IntType) or bt.bits != 8 or bt.signed:
				irank = self.spec.evalConstExpr(type.rankExpr)
				if irank is not None:
					return mult(self.genUnpack(bt, struct, irank))
			rank = genExpr(type.rankExpr, struct)
			
			if isinstance(bt, IntType) or isinstance(bt, FloatType):
				if isinstance(bt, IntType):
					if bt.bits == 8 and not bt.signed:
						return mult('list(bytearray(fp.read(%s)))' % rank)
					fc = ifc[(bt.bits, bt.signed)]
				else:
					fc = ffc[bt.bits]
				return mult('_arrayUnpack(fp, %r, %i, %s)' % (fc, S.calcsize(fc), rank))
			return mult('[%s for _ in xrange(%s)]' % (self.genUnpack(bt, struct, 1), rank))
		elif isinstance(type, Typedef):
			return self.genUnpack(type.otype, struct, count)
		elif isinstance(type, Struct) or isinstance(type, SpecializedType):
			ts = self.spec.structs[type.name]
			depMatch = ''
			if ts.dependencies:
				depMatch = ', ' + u', '.join(sanitize(key if key in struct.dependencies else 'self.' + key) for key in sorted(ts.dependencies.keys()))
			return mult('%s().__unpack__(fp%s)' % (sanitize(type.name), depMatch))
		print '%r %s[%i]' % (type.__class__, type, count)
		assert False
