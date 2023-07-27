.PHONY: help default install uninstall

help: default

default:
	@echo "install                install mbuild to sys"
	@echo "uninstall              uninstall mbuild"

install:
	cp -a mbuild.py /usr/bin/mbuild

uninstall:
	rm -f /usr/bin/mbuild


