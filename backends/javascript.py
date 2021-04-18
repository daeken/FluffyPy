from generator import *
from backend import banner, Backend

headerCode = r'''
let _bytesToCString = bytes => {
	let nind = bytes.indexOf(0);
	if(nind == -1)
		return bytes.map(String.fromCharCode).join('');
	else
		return bytes.slice(nind).map(String.fromCharCode).join('');
};
class BinaryReader {
	constructor(data) {
		if(Array.isArray(data))
			this.dataView = new DataView(new ArrayBuffer(data));
		else if(ArrayBuffer.isView(data))
			this.dataView = new DataView(data.buffer, data.byteOffset, data.byteLength);
		else if(data instanceof ArrayBuffer)
			this.dataView = new DataView(data);
		else
			throw 'Unknown data type for BinaryReader'
		this.length = this.dataView.byteLength;
		this.position = 0;
	}

	skip(amount, value) {
		this.position += amount;
		return value;
	}

	uint8 = () => this.skip(1, this.dataView.getUint8(this.position));
	uint16 = () => this.skip(2, this.dataView.getUint16(this.position));
	uint32 = () => this.skip(4, this.dataView.getUint32(this.position));
	int8 = () => this.skip(1, this.dataView.getInt8(this.position));
	int16 = () => this.skip(2, this.dataView.getInt16(this.position));
	int32 = () => this.skip(4, this.dataView.getInt32(this.position));
	float32 = () => this.skip(4, this.dataView.getFloat32(this.position));
	float64 = () => this.skip(8, this.dataView.getFloat64(this.position));
	readBytes = count => this.skip(count, new Uint8Array(this.dataView.buffer.slice(this.dataView.byteOffset + this.position, this.dataView.byteOffset + this.position + count)));
	readString = len => this.readBytes(len).map(String.fromCharCode).join('');
}
'''.strip()

kwlist = 'break', 'case', 'catch', 'class', 'const', 'continue', 'debugger', 'default', 'delete', 'do', 'else', 'export', 'extends', 'finally', 'for', 'function', 'if', 'import', 'in', 'instanceof', 'new', 'return', 'super', 'switch', 'this', 'throw', 'try', 'typeof', 'var', 'void', 'while', 'with', 'yield'

def sanitize(name):
	if name in kwlist or name[0] in '0123456789':
		return sanitize('_' + name)
	if '<' in name or '>' in name:
		return sanitize(name.replace('<', '_').replace('>', ''))
	return name

isPublic = lambda name: name[0] != '_' and name[0].upper() == name[0]

def genExpr(tree, struct):
	def sub(tree):
		if tree is None:
			return None
		if tree[0] == 'compare':
			return '(%s) %s (%s)' % (sub(tree[1]), tree[2], sub(tree[3]))
		elif tree[0] == 'binary_op':
			return '(%s) %s (%s)' % (sub(tree[1]), tree[2], sub(tree[3]))
		elif tree[0] == 'variable':
			return sanitize(tree[1])
		elif tree[0] == 'value':
			return repr(tree[1])
		elif tree[0] == 'property':
			return '(%s).%s' % (sub(tree[1]), sanitize(tree[2]))
		elif tree[0] == 'cast-to':
			assert isinstance(tree[1], CStringType) # TODO: Add more casts
			return "_bytesToCString(%s)" % sub(tree[2])
		elif tree[0] == 'subscript':
			base = sub(tree[1])
			index = sub(tree[2])
			if isinstance(index, tuple):
				start, end = index
				if start is None:
					if end is None:
						return base
					else:
						return '%s.slice(0, %s)' % (base, end)
				elif end is None:
					return '%s.slice(%s)' % (base, start)
				else:
					return '%s.slice(%s, %s)' % (base, start, end)
			else:
				return '%s[%s]' % (base, index)
		elif tree[0] == 'slice':
			return (sub(tree[1]), sub(tree[2]))
		else:
			print tree
			assert False
	return sub(tree)

class JsBackend(Backend):
	LANGUAGE = 'javascript'
	EXTENSION = 'js'

	def generate(self, spec):
		self.spec = spec
		for line in banner:
			self.writeLine('//', line)
		self.writeLine('//')
		self.writeLine('// DO NOT EDIT')
		self.writeLine('// Generated automatically by Fluffy')

		self.writeLine(headerCode)

		for name, struct in spec.structs.items():
			self.writeLine()
			self.writeLine('export class %s {' % sanitize(name))
			self.indent()
			self.writeLine('constructor(br%s) {' % (', ' + u', '.join(map(sanitize, sorted(struct.dependencies.keys()))) if struct.dependencies else ''))
			self.indent()
			self.writeLine('if(!(br instanceof BinaryReader)) br = new BinaryReader(br);')
			def recur(steps):
				for step in steps:
					if step[0] == 'magic':
						self.writeLine('if(br.readString(%i) != %r) throw \'Magic mismatch in %s\';' % (len(step[1]), str(step[1]), struct.name))
					elif step[0] == 'unsupported':
						self.writeLine('throw \'Unsupported\';')
					elif step[0] == 'unpack':
						unpacker = self.genUnpack(step[1], struct)
						for var in step[2]:
							if isPublic(var):
								self.writeLine('var %s = this.%s = %s;' % (sanitize(var), sanitize(var), unpacker))
							else:
								self.writeLine('var %s = %s;' % (sanitize(var), unpacker))
					elif step[0] == 'assign':
						if isPublic(step[1]):
							self.writeLine('var %s = this.%s = %s;' % (sanitize(step[1]), sanitize(step[1]), genExpr(step[3], struct)))
						else:
							self.writeLine('var %s = %s;' % (sanitize(step[1]), genExpr(step[3], struct)))
					elif step[0] == 'mark_position':
						if isPublic(step[1]):
							self.writeLine('var %s = this.%s = br.position;' % (sanitize(step[1]), sanitize(step[1])))
						else:
							self.writeLine('var %s = br.position;' % sanitize(step[1]))
					elif step[0] == 'seek_abs_scoped':
						oldPos = self.tempvar()
						self.writeLine('let %s = br.position;' % oldPos)
						self.writeLine('br.position = %s;' % genExpr(step[1], struct))
						recur(step[2])
						self.writeLine('br.position = %s;' % oldPos)
					elif step[0] == 'seek_abs':
						self.writeLine('br.position = %s;' % genExpr(step[1], struct))
					elif step[0] == 'match':
						if len(step[2]) == 0:
							continue
						elif len(step[2]) == 1 and step[2][0][0] is None:
							recur(step[2][0][1])
						else:
							self.writeLine('switch(%s) {' % genExpr(step[1], struct))
							for case, body in step[2]:
								if case is not None:
									self.writeLine('case %s:' % genExpr(case, struct))
								else:
									self.writeLine('default:')
								self.indent()
								recur(body)
								self.writeLine('break;')
								self.dedent()
								first = False
							self.writeLine('}')
					elif step[0] == 'if':
						self.writeLine('if(%s) {' % genExpr(step[1], struct))
						self.indent()
						if step[2]:
							recur(step[2])
						self.dedent()
						if step[3]:
							self.writeLine('} else {')
							self.indent()
							recur(step[3])
							self.dedent()
						self.writeLine('}')
					else:
						print step
						assert False
			recur(struct.unpackSteps)
			self.dedent()
			self.writeLine('}')
			self.dedent()
			self.writeLine('}')

	def genUnpack(self, type, struct):
		if isinstance(type, IntType) or isinstance(type, FloatType):
			return 'br.%r()' % type
		elif isinstance(type, ArrayType):
			bt = type.base
			while isinstance(bt, Typedef):
				bt = bt.otype
			rank = genExpr(type.rankExpr, struct)
			if isinstance(bt, IntType) and bt.bits == 8 and not bt.signed:
				return 'br.readBytes(%s)' % rank
			try:
				if type.rankExpr[0] == 'value':
					irank = int(type.rankExpr[1])
					up = self.genUnpack(bt, struct)
					return '[%s]' % u', '.join([up] * irank)
			except:
				pass
			return '[...Array(%s).keys()].map(_ => %s)' % (rank, self.genUnpack(bt, struct))
		elif isinstance(type, Typedef):
			return self.genUnpack(type.otype, struct)
		elif isinstance(type, Struct) or isinstance(type, SpecializedType):
			ts = self.spec.structs[type.name]
			depMatch = ''
			if ts.dependencies:
				depMatch = ', ' + u', '.join(map(sanitize, sorted(ts.dependencies.keys())))
			return 'new %s(br%s)' % (sanitize(type.name), depMatch)
		print '%r %s' % (type.__class__, type)
		assert False
