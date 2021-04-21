import sys
from kdl import *
import tatsu

fslGrammar = r'''
@@whitespace :: /([\t \u00A0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200A\u202F\u205F\u3000\uFFEF])+/

start = stmts:{top_level_stmt} $;

top_level_stmt = @:(typedef_alias | typedef_macro | struct | match_extension) eol;

match_extension = 'match_extension ' extension:string ',' type:type;
typedef_alias = 'typedef ' alias_to:typedef '=' alias_from:type;
typedef = instanced_typedef | named_typedef;
instanced_typedef = base:identifier '<' argnames:','.{ identifier }+;
named_typedef = name:identifier;
typedef_macro = 'typedef ' macro_name:typedef body:block;

type = array:array_type | instanced:instanced_type | named:identifier;
array_type = base:type '[' [rank:value] ']';
instanced_type = base:type '<' args:','.{ value }+ '>';

block = '{' {{newline} @+:block_stmt {newline}} '}';

struct = 'struct ' struct_name:typedef body:block;

block_stmt = @:(if_stmt | while_stmt | match_stmt | for_stmt | delete_stmt | return_values_stmt | return_stmt | break_stmt | continue_stmt | decl_stmt | value_stmt) eol;

if_stmt = 'if' '(' cond:value ')' then:block ['else' _else:block];
while_stmt = 'while' '(' cond:value ')' do:block;
match_stmt = 'match' '(' cond:value ')' '{' {{newline} cases+:(match_case | match_default) {newline}} '}';
match_case = 'case ' case:','.{value}+ ':' body:block eol;
match_default = 'default' ':' default:block eol;
for_stmt = 'for' '(' var:identifier 'in ' iter:value ')' body:block;
delete_stmt = 'delete ' value;
return_values_stmt = 'return ' values:','.{value};
return_stmt = 'return';
break_stmt = 'break';
continue_stmt = 'continue';

decl_stmt = decl_type:type vars:','.{subdecl}+;
subdecl = name:identifier ['=' value:value];

value_stmt = value:value;

value = tuple | group | assign | ternary | binary_op | slice | index | member_access | call | block_call | string | number | variable;
tuple = '(' members+:value ',' members+:','.{value} ')';
group = '(' @:value ')';
assign = lhand:identifier op:('=' | '+=' | '-=' | '*=' | '/=') rhand:value;
ternary = ternary_cond:value '?' left:value ':' right:value;
binary_op = left:value binary_op:('+' | '-' | '*' | '/' | '<' | '<=' | '==' | '!=' | '>=' | '>') right:value; # TODO: Add order of operations!
slice = slice_middle:slice_middle | slice_left:slice_left | slice_right:slice_right;
slice_right = start:value '...';
slice_left = '...' end:value;
slice_middle = start:value '...' end:value;
member_access = base:value '.' member:identifier;
call = callee:value '(' args:','.{value} ')' [block:block];
block_call = callee:value block:block;
index = base:value '[' index:value ']';
variable = variable:identifier;
identifier = !digit /[^\\<>{}();\[\]=,"'\.+\-*!\/?:\t \u00A0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200A\u202F\u205F\u3000\uFFEF\r\n\u0085\u000C\u2028\u2029]+/;
number = hex | octal | binary | decimal;

decimal = decimal:/[+\-]?[0-9][0-9_]*/;
hex = hex:/[+\-]?0x[0-9a-fA-F][0-9a-fA-F_]*/;
octal = octal:/[+\-]?0o[0-7][0-7_]*/;
binary = binary:/[+\-]?0b[01][01_]*/;

string = /'[^']*'/; # TODO: UNFUCK

digit = /[0-9]/;
newline = /(\r\n|[\r\n\u0085\u000C\u2028\u2029])/;
single_line_comment = '//' ->newline;

eol = {$ | newline | ';' | &'}' | single_line_comment}+;
'''

model = tatsu.compile(fslGrammar, name='FslGrammar')

class FluffySpec(object):
	def __init__(self, spec):
		ast = model.parse(spec)
		print ast

def main(sfn):
	fluffy = FluffySpec(file(sfn, 'r').read())

if __name__=='__main__':
	main(*sys.argv[1:])
