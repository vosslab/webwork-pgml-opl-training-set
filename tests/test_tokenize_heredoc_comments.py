#!/usr/bin/env python3

# Standard Library
import os
import sys

# Local modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pg_analyze.tokenize


#============================================


def main() -> None:
	text = (
		"$x = 1; # strip me\n"
		"PGML::Format(<<END_PGML);\n"
		"Inside heredoc # keep me\n"
		"END_PGML\n"
		"$y = 2; # strip me too\n"
	)

	stripped = pg_analyze.tokenize.strip_comments(text)

	expected = (
		"$x = 1; \n"
		"PGML::Format(<<END_PGML);\n"
		"Inside heredoc # keep me\n"
		"END_PGML\n"
		"$y = 2; \n"
	)

	assert stripped == expected


#============================================


if __name__ == "__main__":
	main()
