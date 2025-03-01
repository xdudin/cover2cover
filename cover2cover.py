#!/usr/bin/env python
import os.path
import sys
import time
import xml.etree.ElementTree as ET

changed_class_files = []

def find_lines(j_package, filename): # noqa
    """Return all <line> elements for a given source file in a package."""
    lines = list()
    sources = j_package.findall("sourcefile")
    for source in sources:
        if source.attrib.get("name") == os.path.basename(filename):
            lines = lines + source.findall("line")
    return lines


def line_is_after(jm, start_line):
    return int(jm.attrib.get('line', 0)) > start_line


# noinspection SpellCheckingInspection
def method_lines(jmethod, jmethods, jlines):
    """Filter the lines from the given set of jlines that apply to the given jmethod."""
    start_line = int(jmethod.attrib.get('line', 0))
    larger = list(int(jm.attrib.get('line', 0)) for jm in jmethods if line_is_after(jm, start_line))
    end_line = min(larger) if len(larger) else 99999999

    for jline in jlines:
        if start_line <= int(jline.attrib['nr']) < end_line:
            yield jline


# noinspection SpellCheckingInspection
def convert_lines(j_lines, into):
    """Convert the JaCoCo <line> elements into Cobertura <line> elements, add them under the given element."""
    c_lines = ET.SubElement(into, 'lines')
    for jline in j_lines:
        mb = int(jline.attrib['mb'])
        cb = int(jline.attrib['cb'])
        ci = int(jline.attrib['ci'])

        cline = ET.SubElement(c_lines, 'line')
        cline.set('number', jline.attrib['nr'])
        cline.set('hits', '1' if ci > 0 else '0')  # Probably not true but no way to know from JaCoCo XML file

        if mb + cb > 0:
            percentage = str(int(100 * (float(cb) / (float(cb) + float(mb))))) + '%'
            cline.set('branch', 'true')
            cline.set('condition-coverage', percentage + ' (' + str(cb) + '/' + str(cb + mb) + ')')

            cond = ET.SubElement(ET.SubElement(cline, 'conditions'), 'condition')
            cond.set('number', '0')
            cond.set('type', 'jump')
            cond.set('coverage', percentage)
        else:
            cline.set('branch', 'false')


def path_to_filepath(path_to_class, source_filename):
    return path_to_class[0: path_to_class.rfind("/") + 1] + source_filename


def add_counters(source, target):
    target.set('line-rate', counter(source, 'LINE'))
    target.set('branch-rate', counter(source, 'BRANCH'))
    target.set('complexity', counter(source, 'COMPLEXITY', sum))


def fraction(covered, missed):
    if not covered:
        return 0.0
    return covered / (covered + missed)


# noinspection PyShadowingBuiltins
def sum(covered, missed):
    return covered + missed


# noinspection PyShadowingBuiltins
def counter(source, type, operation=fraction):
    cs = source.findall('counter')
    c = next((ct for ct in cs if ct.attrib.get('type') == type), None)

    if c is not None:
        covered = float(c.attrib['covered'])
        missed = float(c.attrib['missed'])

        return str(operation(covered, missed))
    else:
        return '0.0'


def convert_method(j_method, j_lines):
    c_method = ET.Element('method')
    c_method.set('name', j_method.attrib['name'])
    c_method.set('signature', j_method.attrib['desc'])

    add_counters(j_method, c_method)
    convert_lines(j_lines, c_method)

    return c_method


def convert_class(j_class, j_package):
    c_class = ET.Element('class')
    c_class.set('name', j_class.attrib['name'].replace('/', '.'))
    # sourcefilename is optional, required for multi-module maven/gradle builds
    if 'sourcefilename' in j_class.attrib:
        c_class.set('filename', path_to_filepath(j_class.attrib['name'], j_class.attrib['sourcefilename']))
    else:
        c_class.set('filename', path_to_filepath(j_class.attrib['name'], j_class.attrib['name']))

    all_j_lines = list(find_lines(j_package, c_class.attrib['filename']))

    c_methods = ET.SubElement(c_class, 'methods')
    all_j_methods = list(j_class.findall('method'))
    for j_method in all_j_methods:
        j_method_lines = method_lines(j_method, all_j_methods, all_j_lines)
        c_methods.append(convert_method(j_method, j_method_lines))

    add_counters(j_class, c_class)
    convert_lines(all_j_lines, c_class)

    return c_class


def convert_package(j_package):
    c_package = ET.Element('package')
    c_package.attrib['name'] = j_package.attrib['name'].replace('/', '.')

    c_classes = ET.SubElement(c_package, 'classes')
    for j_class in j_package.findall('class'):

        file_name = path_to_filepath(j_class.attrib['name'], j_class.attrib['sourcefilename']) \
            if 'sourcefilename' in j_class.attrib \
            else path_to_filepath(j_class.attrib['name'], j_class.attrib['name'])

        file_name = file_name.split('/')[-1].split('.')[-2]
        class_name = j_class.attrib['name'].replace('/', '.')

        if file_name in changed_class_files and 'AjcClosure' not in class_name:
            c_classes.append(convert_class(j_class, j_package))

    add_counters(j_package, c_package)

    return c_package


# noinspection PyShadowingBuiltins
def convert_root(source, target, source_roots): # noqa
    try:
        target.set('timestamp', str(int(source.find('sessioninfo').attrib['start']) / 1000))
    except AttributeError as e:
        target.set('timestamp', str(int(time.time() / 1000)))
    sources = ET.SubElement(target, 'sources')
    for s in source_roots:
        ET.SubElement(sources, 'source').text = s

    packages = ET.SubElement(target, 'packages')

    for group in source.findall('group'):
        for package in group.findall('package'):
            packages.append(convert_package(package))

    for package in source.findall('package'):
        packages.append(convert_package(package))

    add_counters(source, target)


def jacoco2cobertura(filename, source_roots): # noqa
    if filename == '-':
        root = ET.fromstring(sys.stdin.read())
    else:
        tree = ET.parse(filename)
        root = tree.getroot()

    into = ET.Element('coverage')
    convert_root(root, into, source_roots)
    print('<?xml version="1.0" ?>')
    print(ET.tostring(into, encoding='unicode'))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: cover2cover.py FILENAME [SOURCE_ROOTS]")
        sys.exit(1)

    filename = sys.argv[1]
    source_roots = sys.argv[2:][0].split('\n') if 2 < len(sys.argv) else '.'

    changed_class_files = os.popen(
        "git --no-pager diff " +
        "origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME..origin/$CI_MERGE_REQUEST_SOURCE_BRANCH_NAME " +
        "--name-only '*.java' | xargs -n1 basename | sed 's/\\..*//'"
    ).read().splitlines()

    jacoco2cobertura(filename, source_roots)
