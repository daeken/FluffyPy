from generator import *
from backend import banner, Backend
import keyword
import struct as S

headerCode = r'''
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
	(32, False) : 'I', 
	(32, True) : 'i', 
}
ffc = {
	32 : 'f', 
	64 : 'd', 
}

class PythonBackend(Backend):
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
			try:
				if type.rankExpr[0] == 'value':
					irank = int(type.rankExpr[1])
					return mult(self.genUnpack(bt, struct, irank))
			except:
				pass
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
