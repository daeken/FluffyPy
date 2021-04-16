from parse import *
import struct as S

class BuiltinType(Type):
	def __init__(self, name, format):
		Type.__init__(self, name, None)
		self.size = S.calcsize(format)
		self.format = '<' + format

	def unpack(self, fp, unpacker):
		return S.unpack(self.format, fp.read(self.size))[0]

class ArrayType(BuiltinType):
	def __init__(self, base, rank):
		Type.__init__(self, u'%s[%i]' % (base.name, rank), None)
		self.base = base
		self.rank = rank

	def unpack(self, fp, unpacker):
		return [unpacker(self.base) for i in xrange(self.rank)]

class CStringType(Type):
	def __init__(self):
		Type.__init__(self, u'c-string', None)

	def castFrom(self, value):
		try:
			end = value.index(0)
		except:
			end = None
		bytes = value[:end]
		return ''.join(map(chr, bytes))

class Context(object):
	def __init__(self, parent=None):
		self.parent = parent
		self.typemaps = {}
		self.variables = {}

	def getType(self, name):
		if name in self.typemaps:
			return self.typemaps[name], self
		if self.parent:
			return self.parent.getType(name)
		return None, None

	def getValue(self, name):
		if name in self.variables:
			return self.variables[name]
		if self.parent:
			return self.parent.getValue(name)
		return None

	def shiftTo(self, frame):
		if isinstance(frame, StructInstance):
			nc = Context(self)
			nc.variables = frame.variables
			return nc
		else:
			raise Exception('Cannot shift to a non-struct context frame!')

class RootContext(Context):
	def __init__(self):
		Context.__init__(self)
		def sbt(name, format):
			self.typemaps[name] = BuiltinType(name, format)
		sbt('uint8', 'B')
		sbt('uint32', 'I')
		sbt('float32', 'f')
		self.typemaps['c-string'] = CStringType()

namedEscapes = {
	'\\': '\\', 
	'/': '/', 
	'r': '\r', 
	'n': '\n', 
	't': '\t', 
	'"': '"', 
	'b': '\b',
	'f': '\f',
}
namedEscapeInverse = {v : k for k, v in namedEscapes.items()}

def formatString(val):
	if '\\' in val and '"' not in val:
		return u'r#"%s"#' % val
	return u'"%s"' % u''.join('\\' + namedEscapeInverse[c] if c in namedEscapeInverse else c for c in val)

def formatValue(value, type):
	if isinstance(value, str):
		return formatString(value)
	elif isinstance(value, int) or isinstance(value, long):
		if type[0] == 'u' and value > 0xFF:
			return hex(value).replace('L', '')
		return str(value).replace('L', '')
	elif isinstance(value, bool):
		return 'true' if value else 'false'
	elif value is None:
		return 'null'
	return unicode(value)

class StructInstance(object):
	def __init__(self, name, variables):
		self.name = name
		self.variables = variables
		self.typedVals = []

	def __str__(self, varname=None):
		if varname:
			ret = '%s { // %s\n' % (varname, self.name)
		else:
			ret = self.name + ' {\n'
		for type, name, value in self.typedVals:
			if name[0] != '_' and name[0].upper() == name[0]:
				if isinstance(value, list):
					if any(isinstance(x, list) or isinstance(x, StructInstance) for x in value):
						ret += '\t%s { // %s\n' % (name, type)
						sub = ''
						for elem in value:
							if isinstance(elem, StructInstance):
								sub += str(elem) + '\n'
							else:
								sub += 'value %s\n' % formatValue(elem, type)
						if len(value):
							ret += u'\n'.join('\t\t' + line for line in sub.rstrip().split('\n')) + '\n'
						ret += '\t}\n'
					else:
						ret += '\t%s %s\n' % (name, u' '.join(formatValue(x, type) for x in value))
				elif isinstance(value, StructInstance):
					sub = value.__str__(name)
					ret += u'\n'.join('\t' + line for line in sub.rstrip().split('\n')) + '\n'
				else:
					ret += '\t%s %s\n' % (name, formatValue(value, type))
		ret += '}'
		return ret

	def dump(self, fp, indent=0, varname=None):
		fp.write('\t' * indent)
		if varname:
			fp.write(varname)
			fp.write(' { // ')
			fp.write(self.name)
			fp.write('\n')
		else:
			fp.write(self.name)
			fp.write(' {\n')
		ws = '\t' * (indent + 1)
		for type, name, value in self.typedVals:
			if name[0] == '_' or name[0].upper() != name[0]:
				continue
			if isinstance(value, list):
				if any(isinstance(x, list) or isinstance(x, StructInstance) for x in value):
					fp.write(ws)
					fp.write(name)
					fp.write(' { // ')
					fp.write(type)
					fp.write('\n')
					tws = '\t' * (indent + 2)
					for elem in value:
						if isinstance(elem, StructInstance):
							elem.dump(fp, indent+2)
						else:
							fp.write(tws)
							fp.write('value ')
							fp.write(formatValue(elem, type))
							fp.write('\n')
					fp.write(ws)
					fp.write('}\n')
				else:
					fp.write(ws)
					fp.write(name)
					for elem in value:
						fp.write(' ')
						fp.write(formatValue(elem, type))
					fp.write('\n')
			elif isinstance(value, StructInstance):
				value.dump(fp, indent+1, name)
			else:
				fp.write(ws)
				fp.write(name)
				fp.write(' ')
				fp.write(formatValue(value, type))
				fp.write('\n')
		fp.write('\t' * indent)
		fp.write('}\n')

class Unpacker(FluffySpec):
	def unpack(self, fp, basetype):
		self.fp = fp
		return self.unpackTypespec(basetype, RootContext())

	def getNamedType(self, typestr, context):
		ctype, tcontext = context.getType(typestr)
		if ctype:
			if isinstance(ctype, Type):
				return ctype
			return self.getNamedType(ctype, tcontext)
		return self.typedefs[typestr]

	def evaluateValue(self, tree, context):
		if tree is None:
			return None
		if tree[0] == 'variable':
			return context.getValue(tree[1])
		elif tree[0] == 'value':
			return tree[1]
		elif tree[0] == 'subscript':
			base = self.evaluateValue(tree[1], context)
			index = self.evaluateValue(tree[2], context)
			if isinstance(index, tuple):
				start, end = index
				return base[start:end]
			else:
				return base[index]
		elif tree[0] == 'slice':
			return self.evaluateValue(tree[1], context), self.evaluateValue(tree[2], context)
		elif tree[0] == 'property':
			context = context.shiftTo(self.evaluateValue(tree[1], context))
			return self.evaluateValue(('variable', tree[2]), context)
		elif tree[0] == 'compare':
			left, right = self.evaluateValue(tree[1], context), self.evaluateValue(tree[3], context)
			return {
				'<' : lambda a, b: a <  b, 
				'<=': lambda a, b: a <= b, 
				'==': lambda a, b: a == b, 
				'!=': lambda a, b: a != b, 
				'>=': lambda a, b: a >= b, 
				'>' : lambda a, b: a >  b, 
			}[tree[2]](left, right)
		print tree
		assert False

	def parseTypespec(self, typeTree, context):
		if isinstance(typeTree, str) or isinstance(typeTree, unicode):
			typeTree = parseTypeString(typeTree)
		def recur(tree):
			if tree[0] == 'named':
				return self.getNamedType(tree[1], context)
			elif tree[0] == 'array':
				return ArrayType(recur(tree[1]), self.evaluateValue(tree[2], context))
			elif tree[0] == 'generic':
				return recur(tree[1]).specialize(map(recur, tree[2]))
			else:
				print tree
				assert False
		return recur(typeTree)

	def unpackTypespec(self, typestr, context):
		type = self.parseTypespec(typestr, context)
		return type.name, self.unpackType(type, context)

	def unpackType(self, type, context, sname=None):
		typename = type.name
		if isinstance(type, SpecializedType):
			context = Context(context)
			for orig, new in zip(type.base.generics, type.genericSubs):
				context.typemaps[orig] = new
			return self.unpackType(type.base, context, sname=type.name)

		if isinstance(type, Typedef):
			return self.unpackTypespec(type.otype, context)[1]
		elif isinstance(type, Struct):
			context = Context(context)
			struct = StructInstance(typename if sname is None else sname, context.variables)
			self.walkStructNodes(type.body, struct, context)
			return struct
		elif isinstance(type, BuiltinType):
			return type.unpack(self.fp, lambda type: self.unpackType(type, context))

	def evaluateArgValue(self, arg, context):
		if isinstance(arg, Symbol):
			return self.evaluateValue(parseValueString(arg.value), context)
		return arg

	def walkStructNodes(self, body, struct, context):
		for node in body:
			if node.name == 'magic':
				assert len(list(node)) == 1 and (isinstance(node[0], str) or isinstance(node[0], unicode))
				data = self.fp.read(len(node[0]))
				if data != node[0]:
					raise Exception('Magic failed: expected %r but got %r' % (node[0], data))
			elif node.name == 'if':
				if not node.children:
					continue
				assert isinstance(node[0], Symbol)
				comparison = self.evaluateArgValue(node[0], context)
				if node.children[0].name == 'then':
					if comparison:
						self.walkStructNodes(node.children[0].children, struct, context)
					else:
						assert node.children[1].name == 'else'
						self.walkStructNodes(node.children[1].children, struct, context)
				elif comparison:
					self.walkStructNodes(node.children, struct, context)
			elif node.name == 'match':
				assert isinstance(node[0], Symbol)
				comparand = self.evaluateArgValue(node[0], context)
				for sub in node.children:
					if sub.name == 'default':
						self.walkStructNodes(sub.children, struct, context)
						break
					elif sub.name == 'case':
						case = self.evaluateArgValue(sub[0], context)
						if comparand == case:
							self.walkStructNodes(sub.children, struct, context)
							break
					else:
						raise Exception(u'Unknown pattern in match: %s' % unicode(sub))
			elif node.children: # Variable created and assigned
				assert len(node.arguments) == 1
				assert isinstance(node[0], Symbol)
				assert len(node.children) == 1
				value = self.evaluateBodyNode(node.children[0], context)
				struct.typedVals.append((node.name, node[0].value, value))
				struct.variables[node[0].value] = value
			else:
				for namesym in node:
					assert isinstance(namesym, Symbol)
					name = namesym.value
					type, value = self.unpackTypespec(node.name, context)
					struct.typedVals.append((type, name, value))
					struct.variables[name] = value

	def evaluateBodyNode(self, node, context):
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
				target = self.parseTypespec(typeArgs[0], context)
				while isinstance(target, Typedef):
					target = self.parseTypespec(target.otype, context)
				return target.castFrom(self.evaluateArgValue(node[0], context))
			else:
				print 'Unknown generic function:', node.name
		elif nameTree[0] == 'named':
			func = nameTree[1]
			if func == 'return':
				assert len(list(node)) == 1
				assert isinstance(node[0], Symbol)
				return self.evaluateArgValue(node[0], context)

		print nameTree
		assert False

def main(sfn, bfn, basetype=None):
	fluffy = Unpacker(file(sfn, 'r'))

	if basetype is None:
		extension = bfn.split('.')[-1]
		if '/' in extension or '\\' in extension:
			extension = None

		if ('extension', extension) in fluffy.fileMatchers:
			basetype = fluffy.fileMatchers[('extension', extension)]
		assert basetype

	tl = fluffy.unpack(file(bfn, 'rb'), basetype)[1]
	print >>sys.stderr, 'Starting dump'
	tl.dump(sys.stdout)

if __name__=='__main__':
	main(*sys.argv[1:])
