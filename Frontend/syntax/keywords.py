from gram import config
from gram import lexer

config.LEXER_COMMENT_TOKEN = ";"
config.LEXER_IGNORE_NEWLINES = False
config.SUPPORT_INDENT = False

word = lexer.words
word.add_group("keywords")
INSTRUCTION_OPCODES = {
    name: name
    for name in (
        "nibbles", "emit", "eword", "save", "load", "reserve", "write_res",
        "drop_res", "emit_res", "frame",
        "pad", "align", "fit", "fit_exact", "fit_not",
        "fit_signed", "fit_signed_exact", "fit_signed_not",
        "vpad", "vreserve", "dpush", "dget", "dpop",
        "bits", "read_bits", "patch_bits", "valign", "mark", "fixup",
    )
}
INSTRUCTION_OPCODES.update({"KW": "kw", "JUMP": "jump"})
INSTRUCTION_OPCODES.update({"JUMPIF": "jumpif", "BREAK": "break", "ERROR": "error"})
for keyword in (
    "table", "end", "block", "define", "rule", "stack", "call",
    "insert", "before",
    "reswidth", "vreswidth", "dist", "vdist",
    "resdir", "resvdir", "resdist", "resvdist", "SIZE", "VSIZE",
    "ALIGNMENT", "LOAD", "LIBRARY",
):
    word.add_keyword(keyword, group="keywords")
word.add_group("variant_keywords")
word.add_keyword("SUPPORTS", group="variant_keywords")
word.add_keyword("ASMVARIANT", group="variant_keywords")
word.add_keyword("END", group="variant_keywords")
word.add_keyword("MODE", group="variant_keywords")
word.add_keyword("SWITCH", group="variant_keywords")
word.add_keyword("ENCAPSULATE", group="variant_keywords")
word.add_keyword("ENTER", group="variant_keywords")
word.add_keyword("EXIT", group="variant_keywords")

word.add_group("token_names")
for token in lexer.Token:
    word.add_keyword(token.name, group="token_names")
