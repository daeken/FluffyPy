banner = r'''
      o__ __o       o__ __o__/_   o          o    o__ __o__/_   o__ __o                o    ____o__ __o____   o__ __o__/_   o__ __o      
     /v     v\     <|    v       <|\        <|>  <|    v       <|     v\              <|>    /   \   /   \   <|    v       <|     v\     
    />       <\    < >           / \o      / \  < >           / \     <\             / \         \o/        < >           / \     <\    
  o/                |            \o/ v\     \o/   |            \o/     o/           o/   \o        |          |            \o/       \o  
 <|       _\__o__   o__/_         |   <\     |    o__/_         |__  _<|           <|__ __|>      < >         o__/_         |         |> 
  \          |     |            / \    \o  / \   |             |       \          /       \       |          |            / \       //  
    \         /    <o>           \o/     v\ \o/  <o>           <o>       \o      o/         \o     o         <o>           \o/      /    
     o       o      |             |       <\ |    |             |         v\    /v           v\   <|          |             |      o     
     <\__ __/>     / \  _\o__/_  / \        < \  / \  _\o__/_  / \         <\  />             <\  / \        / \  _\o__/_  / \  __/>
'''.split('\n')[1:-1]

class Backend(object):
	indentStr = '\t'

	def __init__(self, fp):
		self.fp = fp
		self.curIndent = 0
		self.tempI = 0

	def writeLine(self, *args):
		self.fp.write(self.indentStr * self.curIndent + u' '.join(args) + '\n')

	def indentBlock(self, data, count=1):
		return u'\n'.join(indentStr * count + line for line in data.split(u'\n'))

	def indent(self):
		self.curIndent += 1

	def dedent(self):
		self.curIndent -= 1

	def tempvar(self):
		self.tempI += 1
		return '_temp_%i' % self.tempI
