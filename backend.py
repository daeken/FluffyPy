banner = r'''

$$$$$$$$\ $$\            $$$$$$\   $$$$$$\            
$$  _____|$$ |          $$  __$$\ $$  __$$\           
$$ |      $$ |$$\   $$\ $$ /  \__|$$ /  \__|$$\   $$\ 
$$$$$\    $$ |$$ |  $$ |$$$$\     $$$$\     $$ |  $$ |
$$  __|   $$ |$$ |  $$ |$$  _|    $$  _|    $$ |  $$ |
$$ |      $$ |$$ |  $$ |$$ |      $$ |      $$ |  $$ |
$$ |      $$ |\$$$$$$  |$$ |      $$ |      \$$$$$$$ |
\__|      \__| \______/ \__|      \__|       \____$$ |
                                            $$\   $$ |
                                            \$$$$$$  |
                                             \______/ 
'''.split('\n')[1:-1]

class Backend(object):
	indentStr = '\t'

	def __init__(self, fp, namespace):
		self.fp = fp
		self.namespace = namespace
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
