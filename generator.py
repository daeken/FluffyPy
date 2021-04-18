from parse import *
from collections import OrderedDict

class StructInstance(object):
	def __init__(self, name):
		self.name = name
		self.dependencies = {}
		self.fields = OrderedDict()
		self.unpackSteps = []

class IntType(Type):
	def __init__(self, bits, signed):
		Type.__init__(self, '%sint%i' % ('' if signed else 'u', bits), None)
		self.bits = bits
		self.signed = signed

	def equivalent(self, other):
		if not isinstance(other, IntType):
			return False
		return self.bits == other.bits and self.signed == other.signed

class FloatType(Type):
	def __init__(self, bits):
		Type.__init__(self, 'float%i' % bits, None)
		self.bits = bits

class ArrayType(Type):
	def __init__(self, base, rankExpr):
		Type.__init__(self, u'%s[]' % base, None)
		self.base = base
		self.rankExpr = rankExpr
		self.name = u'%s[%r]' % (base.name, rankExpr)

	def equivalent(self, other):
		if not isinstance(other, ArrayType):
			return False
		return self.base.equivalent(other.base)

class CStringType(Type):
	def __init__(self):
		Type.__init__(self, 'c-string', None)

class Generator(FluffySpec):
	def __init__(self, specd, backend):
		FluffySpec.__init__(self, specd)

		self.builtinTypes = dict(
			uint8=IntType(8, False),
			uint16=IntType(16, False),
			uint32=IntType(32, False),
			uint64=IntType(64, False),
			int8=IntType(8, True),
			int16=IntType(16, True),
			int32=IntType(32, True),
			int64=IntType(64, True),
			float32=FloatType(32),
			float64=FloatType(64),
		)
		self.builtinTypes['c-string'] = CStringType()

		for name, type in self.typedefs.items():
			if isinstance(type, Typedef):
				if not isinstance(type.otype, Type):
					if not type.generics:
						self.typemap = {}
						type.otype = self.parseTypespec(type.otype)

		self.buildStructs()
		self.cascadeDeps()
		self.backpropDepTypes()

		backend.generate(self)

	def unifyTypes(self, typelist):
		out = []
		for type in typelist:
			if type is None or any(type.equivalent(x) for x in out):
				continue
			out.append(type)
		return out

	def backpropDepTypes(self):
		changed = False
		fixup = [(x, None) for x in self.structs.keys()]
		fixed = set()
		while fixup:
			name, dname = fixup.pop(0)
			if (name, dname) in fixed:
				continue
			fixed.add((name, dname))
			def recur(type):
				if isinstance(type, ArrayType):
					return recur(type.base)
				elif isinstance(type, Struct) or isinstance(type, SpecializedType):
					subchange = False
					if type.name in self.structs:
						ts = self.structs[type.name]
						for fname, ftype in ts.dependencies.items():
							if fname in struct.fields or (fname in struct.dependencies and struct.dependencies[fname] is not None):
								types = struct.fields[fname] if fname in struct.fields else [struct.dependencies[fname]]
								ut = self.unifyTypes(types + [ftype])
								if len(ut) != 1:
									raise Exception('Could not unify disparate types: %r %r' % (types, ftype))
								ts.dependencies[fname] = ut[0]
								subchange = True
								fixup.append((type.name, fname))
					return subchange
				elif isinstance(type, Typedef):
					return recur(type.otype)
			struct = self.structs[name]
			for fn, fts in struct.fields.items():
				changed = False
				for ft in fts:
					changed = changed or recur(ft)
				if changed:
					fixup.append((name, fn))

		for struct in self.structs.values():
			if None in struct.dependencies.values():
				raise Exception('Unresolved reference(s) in struct %s: %r' % (struct.name, [name for name, type in struct.dependencies.items() if type is None]))

	def cascadeDeps(self):
		fixed = set()
		def fix(name):
			if name in fixed:
				return
			fixed.add(name)
			if name not in self.structs:
				return
			struct = self.structs[name]
			def recur(type):
				if isinstance(type, ArrayType):
					return recur(type.base)
				elif isinstance(type, Struct) or isinstance(type, SpecializedType):
					if type.name in self.structs:
						fix(type.name)
						return self.structs[type.name].dependencies
				elif isinstance(type, Typedef):
					return recur(type.otype)
				return {}
			for fn, fts in struct.fields.items():
				for ft in fts:
					for tname, ttype in recur(ft).items():
						assert ttype is None
						if tname not in struct.dependencies and tname not in struct.fields:
							struct.dependencies[tname] = None
		for name in self.structs.keys():
			fix(name)

	def buildStructs(self):
		self.structs = {}
		buildQueue = list(self.typedefs.values())
		built = set()
		def need(type):
			if isinstance(type, ArrayType):
				need(type.base)
			elif isinstance(type, SpecializedType) or isinstance(type, Struct):
				buildQueue.append(type)
			elif isinstance(type, Typedef):
				need(type.otype)
		while buildQueue:
			type = buildQueue.pop(0)
			if type.name in built:
				continue
			built.add(type.name)
			if not isinstance(type, Struct) and not isinstance(type, SpecializedType):
				continue
			if type.generics and not isinstance(type, SpecializedType):
				continue
			if isinstance(type, SpecializedType):
				if not isinstance(type.base, Struct):
					continue
				self.typemap = {k:v for k, v in zip(type.base.generics, type.genericSubs)}
			else:
				self.typemap = {}

			struct = self.struct = self.structs[type.name] = StructInstance(type.name)
			def doRecur(body):
				return [x for x in map(recur, body) if x is not None]
			def recur(node):
				if node.name == 'magic':
					assert len(list(node)) == 1 and (isinstance(node[0], str) or isinstance(node[0], unicode))
					return ('magic', node[0])
				elif node.name == 'if':
					if node.children[0].name == 'then':
						then, _else = doRecur(node.children[0].children), doRecur(node.children[1].children) if len(node.children) > 1 else []
					else:
						then, _else = doRecur(node.children), []
					return ('if', self.parseArgValue(node[0]), then, _else)
				elif node.name == 'match':
					body = []
					default = None
					for snode in node.children:
						if snode.name == 'default':
							default = doRecur(snode.children)
						else:
							body.append((self.parseArgValue(snode[0]), doRecur(snode.children)))
					if default:
						body.append((None, default))
					return ('match', self.parseArgValue(node[0]), body)
				elif node.name == 'unsupported':
					return 'unsupported',
				elif node.name == 'mark_position':
					assert isinstance(node[0], Symbol)
					name = node[0].value
					if name not in struct.fields:
						struct.fields[name] = []
					nt = self.builtinTypes['uint64']
					if nt not in struct.fields[name]:
						struct.fields[name].append(nt)
					return ('mark_position', name)
				elif node.name == 'seek_abs':
					value = self.parseArgValue(node[0])
					if node.children:
						return ('seek_abs_scoped', value, doRecur(node.children))
					else:
						return ('seek_abs', value)
				elif node.name == 'seek_rel':
					value = ('binary_op', self.parseArgValue(node[0]), '+', self.parseArgValue(node[1]))
					if node.children:
						return ('seek_abs_scoped', value, doRecur(node.children))
					else:
						return ('seek_abs', value)
				elif node.children:
					assert isinstance(node[0], Symbol)
					name = node[0].value
					assert len(node.children) == 1
					nt = self.parseTypespec(node.name)
					if name not in struct.fields:
						struct.fields[name] = []
					if nt not in struct.fields[name]:
						struct.fields[name].append(nt)
					return ('assign', name, nt, self.parseBodyNode(node.children[0]))
				else:
					type = self.parseTypespec(node.name)
					need(type)
					vars = []
					for namesym in node:
						assert isinstance(namesym, Symbol)
						name = namesym.value
						if name not in struct.fields:
							struct.fields[name] = []
						if type not in struct.fields[name]:
							struct.fields[name].append(type)
						vars.append(name)
					return ('unpack', type, vars)
				print node
				assert False
			struct.unpackSteps = doRecur(type.body if isinstance(type, Struct) else type.base.body)

		for struct in self.structs.values():
			for fname, ftypes in struct.fields.items():
				struct.fields[fname] = self.unifyTypes(ftypes)

	def getNamedType(self, name):
		if name in self.typemap:
			rt = self.typemap[name]
			if not isinstance(rt, Type):
				return self.parseTypespec(rt)
			return rt
		if name in self.typedefs:
			return self.typedefs[name]
		if name in self.builtinTypes:
			return self.builtinTypes[name]
		raise Exception('Unknown type: %s' % name)

	def parseTypespec(self, typeTree):
		if isinstance(typeTree, str) or isinstance(typeTree, unicode):
			typeTree = parseTypeString(typeTree)
		def recur(tree):
			if isinstance(tree, Type):
				return tree
			if tree[0] == 'named':
				return self.getNamedType(tree[1])
			elif tree[0] == 'array':
				return ArrayType(recur(tree[1]), self.parseValue(tree[2]))
			elif tree[0] == 'generic':
				return recur(tree[1]).specialize(map(recur, tree[2]))
			else:
				print tree
				assert False
		return recur(typeTree)

	def parseArgValue(self, arg):
		if isinstance(arg, Symbol):
			return self.parseValue(parseValueString(arg.value))
		else:
			return ('value', arg)

	def parseValue(self, tree):
		if tree is None:
			return ('value', None)
		elif tree[0] == 'variable':
			self.needVariable(tree[1])
		elif tree[0] == 'subscript':
			self.parseValue(tree[1])
			self.parseValue(tree[2])
		elif tree[0] == 'slice':
			self.parseValue(tree[1])
			self.parseValue(tree[2])
		elif tree[0] == 'property':
			self.parseValue(tree[1])
		elif tree[0] == 'compare':
			self.parseValue(tree[1])
			self.parseValue(tree[3])
		elif tree[0] == 'value':
			pass
		else:
			print tree
			assert False
		return tree

	def parseBodyNode(self, node):
		nameTree = parseTypeString(node.name)
		if nameTree[0] == 'generic':
			func = nameTree[1]
			typeArgs = nameTree[2]
			assert func[0] == 'named'
			func = func[1]
			if func == 'cast':
				assert len(typeArgs) == 1
				assert len(list(node)) == 1
				assert isinstance(node[0], Symbol)
				target = self.parseTypespec(typeArgs[0])
				while isinstance(target, Typedef):
					target = self.parseTypespec(target.otype)
				return ('cast-to', target, self.parseArgValue(node[0]))
			else:
				print 'Unknown generic function:', node.name
		elif nameTree[0] == 'named':
			func = nameTree[1]
			if func == 'return':
				assert len(list(node)) == 1
				assert isinstance(node[0], Symbol)
				return self.parseArgValue(node[0])

		print nameTree
		assert False

	def needVariable(self, name):
		if name in self.struct.fields:
			return
		self.struct.dependencies[name] = None

def main(sfn):
	from backends import PythonBackend
	fluffy = Generator(file(sfn, 'r'), PythonBackend(file('testoutput.py', 'w')))

if __name__=='__main__':
	main(*sys.argv[1:])

