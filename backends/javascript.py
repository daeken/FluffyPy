from generator import *
from backend import banner, Backend

headerCode = r'''
let _bytesToString = bytes => bytes.map(c => String.fromCharCode(c)).join('');
let _bytesToCString = bytes => {
	let nind = bytes.indexOf(0);
	if(nind == -1)
		return _bytesToString(bytes);
	else
		return _bytesToString(bytes.slice(0, nind));
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

	uint8 = () => this.skip(1, this.dataView.getUint8(this.position, true));
	uint16 = () => this.skip(2, this.dataView.getUint16(this.position, true));
	uint32 = () => this.skip(4, this.dataView.getUint32(this.position, true));
	int8 = () => this.skip(1, this.dataView.getInt8(this.position, true));
	int16 = () => this.skip(2, this.dataView.getInt16(this.position, true));
	int32 = () => this.skip(4, this.dataView.getInt32(this.position, true));
	float32 = () => this.skip(4, this.dataView.getFloat32(this.position, true));
	float64 = () => this.skip(8, this.dataView.getFloat64(this.position, true));
	readBytes = count => this.skip(count, Array.from(new Uint8Array(this.dataView.buffer.slice(this.dataView.byteOffset + this.position, this.dataView.byteOffset + this.position + count))));
	readString = len => _bytesToString(this.readBytes(len));
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
			if tree[1] in struct.fields:
				return 'this.%s' % sanitize(tree[1])
			else:
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
			for fn in struct.fields:
				if not isPublic(fn):
					self.writeLine('Object.defineProperty(this, \'%s\', {enumerable: false, writable: true});' % sanitize(fn))
			def recur(steps):
				for step in steps:
					if step[0] == 'magic':
						self.writeLine('if(br.readString(%i) != %r) throw \'Magic mismatch in %s\';' % (len(step[1]), str(step[1]), struct.name))
					elif step[0] == 'unsupported':
						self.writeLine('throw \'Unsupported\';')
					elif step[0] == 'unpack':
						unpacker = self.genUnpack(step[1], struct)
						for var in step[2]:
							self.writeLine('this.%s = %s;' % (sanitize(var), unpacker))
					elif step[0] == 'assign':
						self.writeLine('this.%s = %s;' % (sanitize(step[1]), genExpr(step[3], struct)))
					elif step[0] == 'mark_position':
						self.writeLine('this.%s = br.position;' % (sanitize(step[1])))
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
				depMatch = ', ' + u', '.join(sanitize(key if key in struct.dependencies else 'this.' + key) for key in sorted(ts.dependencies.keys()))
			return 'new %s(br%s)' % (sanitize(type.name), depMatch)
		print '%r %s' % (type.__class__, type)
		assert False
