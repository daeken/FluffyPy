from __future__ import print_function
import argparse, io, sys
from generator import *
from unpack import Unpacker
from backends import backends

parser = argparse.ArgumentParser(description='Work with Fluffy specifications')
parser.add_argument('specification', metavar='spec.kdl', type=str, help='Fluffy spec in KDL format')
parser.add_argument('-o', '--out', dest='output', metavar='FILE', type=str, help='output file')
parser.add_argument('-u', '--unpack', dest='unpack', metavar='FILE', type=str, help='input binary to parse')
parser.add_argument('-l', '--language', dest='language', help='language to generate (choices: %s)' % ', '.join(x.LANGUAGE for x in backends))
parser.add_argument('-s', '--struct', dest='struct', help='top-level struct to begin unpacking')
args = parser.parse_args()

if args.unpack:
	unpacker = Unpacker(io.open(args.specification, 'r', encoding='utf-8'))
	if args.struct:
		start = args.struct
	else:
		ext = args.unpack.rsplit('.', 1)[-1].lower()
		if ('extension', ext) in unpacker.fileMatchers:
			start = unpacker.fileMatchers[('extension', ext)]
		else:
			print('Cannot determine top-level struct for unpacking -- specify it', file=sys.stderr)
			sys.exit(1)
	doc = unpacker.unpack(open(args.unpack, 'rb'), start)[1]
	if args.output:
		tgt = io.open(args.output, 'w', encoding='utf-8')
		if sys.version_info[0] == 2:
			write = tgt.write
			tgt.write = lambda x: write(unicode(x))
	else:
		tgt = sys.stdout
	doc.dump(tgt)
else:
	backend = None
	if args.language:
		for be in backends:
			if args.language.lower() == be.LANGUAGE:
				backend = be
				break
		if backend is None:
			print('Unknown language specified -- valid choices: %s' % ', '.join(x.LANGUAGE for x in backends), file=sys.stderr)
			sys.exit(1)
	if args.output:
		ext = args.output.rsplit('.', 1)[-1].lower()
		for be in backends:
			if ext == be.EXTENSION:
				backend = be
				break
	if backend is None:
		print('Could not determine language for generation -- specify it', file=sys.stderr)
		sys.exit(1)

	Generator(io.open(args.specification, 'r', encoding='utf-8'), backend(io.open(args.output, 'w', encoding='utf-8') if args.output else sys.stdout))
