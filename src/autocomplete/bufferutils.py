# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2010-2017  Sergey Satskiy <sergey.satskiy@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""Various editor buffer related utilities"""

import re
import time
from cdmpyparser import getBriefModuleInfoFromMemory


WORD_PATTERN = '\w+'
WORD_REGEXP = re.compile(WORD_PATTERN)
EDITOR_TAG_TIMEOUT = 0.5


def getEditorTags(editor, exclude=None, excludePythonKeywords=False):
    """Builds a list of the tags in the editor.
       The current line could be excluded.
       The only tags are included which start with prefix
    """
    start = time.time()

    excludeSet = set()
    if exclude:
        excludeSet.add(exclude)
    if excludePythonKeywords:
        # Note: 2 characters words will be filtered unconditionally
        excludeSet.update(["try", "for", "and", "not"])

    result = set()
    for line in editor.lines:
        for match in WORD_REGEXP.findall(line):
            if len(match) > 2:
                if match not in excludeSet:
                    result.add(match)
        if time.time() - start > EDITOR_TAG_TIMEOUT:
            # Do not freeze longer than that
            break

    # If a cursor is in a middle of the word then the current word is not what
    # you need.
    if editor.getWordAfterCursor() == '':
        result.discard(editor.getWordBeforeCursor())
    return result


class TextCursorContext:

    """Holds the text cursor context for a python file"""

    GlobalScope = 1
    FunctionScope = 2
    ClassScope = 3
    ClassMethodScope = 4

    def __init__(self):
        self.levels = []    # Each item is [infoObj, scope type]
        self.length = 0

    def addFunction(self, infoObj):
        """Adds nested function"""
        if self.length == 0:
            self.levels.append([infoObj, self.FunctionScope])
        else:
            if self.levels[self.length - 1][1] == self.ClassScope:
                self.levels.append([infoObj, self.ClassMethodScope])
            else:
                self.levels.append([infoObj, self.FunctionScope])
        self.length += 1

    def getScope(self):
        """Provides the deepest scope type"""
        if self.length == 0:
            return self.GlobalScope
        return self.levels[self.length - 1][1]

    def getInfoObj(self):
        """Provides the deepest info object"""
        if self.length == 0:
            return None
        return self.levels[self.length - 1][0]

    def addClass(self, infoObj):
        """Adds nested class"""
        self.levels.append([infoObj, self.ClassScope])
        self.length += 1

    def __scopeToString(self, scope):
        """Converts scope constant to a string"""
        if scope == self.GlobalScope:
            return "GlobalScope"
        if scope == self.FunctionScope:
            return "FunctionScope"
        if scope == self.ClassScope:
            return "ClassScope"
        if scope == self.ClassMethodScope:
            return "ClassMethodScope"
        return "UnknownScope"

    def __str__(self):
        """Converts context to a string representation"""
        retval = ""
        if self.length == 0:
            retval = "GlobalScope"

        first = True
        for level in self.levels:
            if first:
                first = False
            else:
                retval += " -> "
            retval += self.__scopeToString(level[1]) + \
                ":" + level[0].name + ":" + str(level[0].line)
        return retval

    def getLastScopeLine(self):
        """Provides the last scope line"""
        if self.length == 0:
            raise Exception("No scopes found")
        return self.levels[self.length - 1][0].colonLine

    def stripLevels(self, nonSpacePos):
        """Strips the levels depending on the position"""
        maxLevels = int(nonSpacePos / 4)
        if maxLevels < self.length:
            self.levels = self.levels[:maxLevels]
            self.length = maxLevels


def _IdentifyScope(infoObject, context, cursorLine, cursorPos, skipDef):
    """Searches for the hierarchy"""
    # Find the closest class definition (global level for the first call)
    nearestClassLine = -1
    nearestClassInfo = None
    for klass in infoObject.classes:
        onDef = _isOnDefinitionLine(klass, cursorLine, cursorPos)
        if skipDef:
            if onDef:
                return
            if klass.line > nearestClassLine and klass.line < cursorLine:
                nearestClassLine = klass.line
                nearestClassInfo = klass
        else:
            if onDef:
                context.addClass(klass)
                return
            if klass.line > nearestClassLine and klass.line < cursorLine:
                nearestClassLine = klass.line
                nearestClassInfo = klass

    # Find the closest function definition (global level for the first call)
    nearestFuncLine = -1
    nearestFuncInfo = None
    for func in infoObject.functions:
        onDef = _isOnDefinitionLine(func, cursorLine, cursorPos)
        if skipDef:
            if onDef:
                return
            if func.line > nearestClassLine and \
               func.line > nearestFuncLine and \
               func.line <= cursorLine:
                nearestFuncLine = func.line
                nearestFuncInfo = func
        else:
            if onDef:
                context.addFunction(func)
                return
            if func.line > nearestClassLine and \
               func.line > nearestFuncLine and \
               func.line <= cursorLine:
                nearestFuncLine = func.line
                nearestFuncInfo = func

    if nearestClassLine == -1 and nearestFuncLine == -1:
        # No definitions before the line
        return

    # Check nested objects
    if nearestClassLine > nearestFuncLine:
        context.addClass(nearestClassInfo)
        _IdentifyScope(nearestClassInfo, context,
                       cursorLine, cursorPos, skipDef)
    else:
        context.addFunction(nearestFuncInfo)
        _IdentifyScope(nearestFuncInfo, context,
                       cursorLine, cursorPos, skipDef)


def _getFirstNonSpacePos(text):
    """Provides the index of the first non-space character in the given line"""
    for pos in range(len(text)):
        if text[pos] not in [' ', '\n', '\r']:
            return pos
    return -1


def _endsWithTripleQuotedString(editor, line, pos):
    """True if the position is a triple quoted string literal"""
    return False
    editorPos = editor.positionFromLineIndex(line, pos)
    return editor.styleAt(editorPos) in \
        [QsciLexerPython.TripleDoubleQuotedString,
         QsciLexerPython.TripleSingleQuotedString]


def getContext(editor, info=None,
               skipBlankLinesBack=False, skipDef=True):
    """Detects the context at the text cursor position.

    skipBlankLinesBack == False => current cursor position is used
    skipBlankLinesBack == True => skip blank lines back and use the first 
                                  non-blank line as the cursor position.
    skipDef == True => treat a definition as belonging to an upper
                       level context (not included into the context stack)
    skipDef == False => treat a definition as starting a context level
                        (included into the context stack as the last one)
    """
    # It is expected that this is a python editor.
    # If non-python editor is given, then a global context is provided

    context = TextCursorContext()

    if not editor.isPythonBuffer():
        return context

    # It's not the first position, so the parsed module info is required
    if info is None:
        info = getBriefModuleInfoFromMemory(editor.text)

    line, pos = editor.cursorPosition
    if skipBlankLinesBack == True:
        while line >= 0:
            text = editor.lines[line]
            trimmedText = text.strip()
            if trimmedText != "":
                pos = len(text.rstrip())
                break
            line -= 1
        if line < 0:
            line = 0
            pos = 0

    _IdentifyScope(info, context, line + 1, pos, skipDef)

    if not skipDef:
        if _getDefinitionObject(info, line + 1, pos) is not None:
            return context

    if context.length == 0:
        return context

    continueLine = False
    currentLine = context.getLastScopeLine() + 1
    for currentLine in range(context.getLastScopeLine(),
                             len(editor.lines)):
        if currentLine == line:
            break

        text = editor.lines[currentLine]
        trimmedText = text.strip()
        if continueLine == False:
            if trimmedText == "" or trimmedText.startswith("#"):
                continue

            # Here: there must be characters in the line
            nonSpacePos = _getFirstNonSpacePos(text)
            context.stripLevels(nonSpacePos)
            if context.length == 0:
                return context

        if trimmedText.endswith(",") or trimmedText.endswith('\\') or \
           _endsWithTripleQuotedString(editor, currentLine, len(text) - 1):
            continueLine = True
        else:
            continueLine = False

    if continueLine:
        context.stripLevels(nonSpacePos)
    else:
        nonSpacePos = _getFirstNonSpacePos(editor.lines[line])
        if nonSpacePos == -1:
            context.stripLevels(pos)
        else:
            context.stripLevels(min(pos, nonSpacePos))
    return context


def _isOnDefinitionLine(infoObj, line, pos):
    """Returns True if the cursor is within the definition line of the
       given object (class or function)
       Line and pos are 1-based
    """
    lowLimit = infoObj.keywordLine << 16
    upLimit = (infoObj.colonLine << 16) + infoObj.colonPos
    current = (line << 16) + pos
    for decor in infoObj.decorators:
        candidate = (decor.line << 16) + decor.pos
        if candidate < lowLimit:
            lowLimit = candidate
    if current >= lowLimit and current <= upLimit:
        return True
    return False


def _getDefinitionObject(info, line, pos):
    """Returns an object (class or function) if the cursor is on the definition
       line. None if it is not.
       Line and pos are 1-based
    """
    for cls in info.classes:
        if _isOnDefinitionLine(cls, line, pos):
            return cls
        obj = _getDefinitionObject(cls, line, pos)
        if obj:
            return obj
    for func in info.functions:
        if _isOnDefinitionLine(func, line, pos):
            return func
        obj = _getDefinitionObject(func, line, pos)
        if obj:
            return obj
    return None


# Note: docstrings are considered as comments
def isStringLiteral(editor, line=None, pos=None):
    """True if the position is inside a string literal"""
    if line is None or pos is None:
        line, pos = editor.cursorPosition
    text = editor.lines[line]
    if not text.strip():
        return False

    return editor.styleAt(pos) in \
                    [QsciLexerPython.TripleDoubleQuotedString,
                     QsciLexerPython.TripleSingleQuotedString,
                     QsciLexerPython.DoubleQuotedString,
                     QsciLexerPython.SingleQuotedString,
                     QsciLexerPython.UnclosedString]


# Note: The docstrings are considered as comments as well
def isComment(editor, line=None, pos=None):
    """True if the position is inside a comment or a docstring"""
    if line is None or pos is None:
        line, pos = editor.cursorPosition
    text = editor.lines[line]
    if not text.strip():
        return False
    if pos >= len(text):
        pos = len(text) - 1

    return editor.isComment(line, pos)


def isImportLine(editor):
    """True if the current line is a part of an import line"""
    line, pos = editor.cursorPosition
    text = editor.lines[line]
    if not text.strip():
        return False, None
    if pos >= len(text):
        pos = len(text) - 1

    if editor.isComment(line, pos):
        return False, None
    if editor.isStringLiteral(line, pos):
        return False, None

    return False, None


    # Find the beginning of the line
    while True:
        if line == 0:
            break
        prevLine = editor.lines[line - 1]

    while True:
        if line == 0:
            break
        prevLine = editor.lines[line - 1].strip()
        if not prevLine.endswith('\\') and not prevLine.endswith(','):
            break
        line -= 1

    text = editor.lines[line].strip()
    if text.startswith("import ") or text.startswith("from ") or \
       text.startswith("import\\") or text.startswith("from\\"):
        if not isStringLiteral(editor,
                               editor.positionFromLineIndex(line, 0)):
            return True, line
    return False, None


def _skipSpacesBackAtPos(editor, pos):
    """Skips the spaces"""
    while pos >= 0:
        if editor.charAt(pos) in [' ', '\t', '\r', '\n', '\\']:
            pos = editor.positionBefore(pos)
            continue
        return pos
    return pos


def _skipIdentifierBackAtPos(editor, pos):
    """Skips an identifier"""
    while pos >= 0:
        ch = editor.charAt(pos)
        if ch.isalnum() or ch == '_':
            pos = editor.positionBefore(pos)
            continue
        return pos
    return pos


def getCallPosition(editor, pos=None):
    """It is going to be used for calltips. It provides a position
       of the last character of the function name is (or None if not found)
    """
    if pos is None:
        pos = editor.cursorPosition

    if editor.charAt(pos) in [')', '(']:
        pos = editor.positionBefore(pos)
        if pos <= 0:
            return None

    level = 0
    startLine, _ = editor.lineIndexFromPosition(pos)
    while pos > 0:
        if isStringLiteral(editor, pos):
            pos = editor.positionBefore(pos)
            continue
        ch = editor.charAt(pos)
        if ch == ')':
            level += 1
        elif ch == '(':
            if level == 0:
                # It could be the beginning of a tuple parameter, so check the
                # previous char. If it is a comma, then we need to continue.
                checkPos = _skipSpacesBackAtPos(editor,
                                                editor.positionBefore(pos))
                if checkPos <= 0:
                    return None

                # Found first meaningful character before the bracket
                ch = editor.charAt(checkPos)
                if ch.isalnum() or ch == '_':
                    if __isDefinition(editor, checkPos):
                        return None
                    return checkPos

                # There are a few options here:
                # , => need to continue
                # = => could be a keyworded parameter value
                # ( => tuple in a tuple
                # The rest is bad syntax
                if ch in [',', '(']:
                    pos = checkPos
                    continue
                if ch == '=':
                    checkPos = _skipSpacesBackAtPos(
                        editor, editor.positionBefore(checkPos))
                    checkPos = _skipIdentifierBackAtPos(editor, checkPos)
                    checkPos = _skipSpacesBackAtPos(editor, checkPos)
                    if checkPos <= 0:
                        return None
                    if editor.charAt(checkPos) in [',', '(']:
                        pos = checkPos
                        continue
                return None
            level -= 1
        elif ch in ['\n', '\r']:
            # It makes sense to check if it is a time to stop searching
            curLine, _ = editor.lineIndexFromPosition(pos)
            if curLine < startLine:
                lineContent = editor.text(curLine + 1).strip()
                if lineContent.startswith("def" ) or \
                   lineContent.startswith("class" ) or \
                   lineContent.startswith("def\\") or \
                   lineContent.startswith("class\\"):
                    # It does not make sense to search beyond a class or
                    # a function definition
                    return None
        pos = editor.positionBefore(pos)

    return None


def __isDefinition(editor, pos):
    """Used as a sanity check together with getCallPosition(...).
       It could be the case that the detected call is a definition of a
       class or a function and thus they should not have a calltip
    """
    return editor.styleAt(pos) in [QsciLexerPython.ClassName,
                                   QsciLexerPython.FunctionMethodName]


def getCommaCount(editor, startPos, endPos):
    """Used for calltips. Provides the # of commas before the end position"""
    commas = 0
    level = 0

    while editor.charAt(startPos) != '(':
        startPos = editor.positionAfter(startPos)
    # Step to the first character inside the call brackets
    startPos = editor.positionAfter(startPos)

    while startPos < endPos:
        if isStringLiteral(editor, startPos):
            startPos = editor.positionAfter(startPos)
            continue
        ch = editor.charAt(startPos)
        if ch in ['(', '[', '{']:
            level += 1
        elif ch in [')', ']', '}']:
            level -= 1
        elif ch == ',' and level == 0:
            commas += 1
        startPos = editor.positionAfter(startPos)
    return commas


def getItemForDisplayPath(info, displayPath):
    """Info is what the parser provides.
       displayPath is a list of what displayed in a tree.
       The method provides the certain item from the info if it is still there
    """
    # Ugly but helps to avoid initialization obstacles
    from ui.viewitems import (FunctionItemType, ClassesItemType,
                              FunctionsItemType, ImportsItemType,
                              InstanceAttributesItemType,
                              StaticAttributesItemType, GlobalsItemType,
                              CodingItemType, ImportWhatItemType,
                              DecoratorItemType)
    for (itemType, pathItem) in displayPath:
        if itemType == ClassesItemType:
            info = info.classes
        elif itemType == FunctionsItemType:
            info = info.functions
        elif itemType == ImportsItemType:
            info = info.imports
        elif itemType == InstanceAttributesItemType:
            info = info.instanceAttributes
        elif itemType == StaticAttributesItemType:
            info = info.classAttributes
        elif itemType == GlobalsItemType:
            info = info.globals
        elif itemType == CodingItemType:
            return info.encoding
        else:
            # That's a name, find it in the container
            if itemType == ImportWhatItemType:
                info = info.what
            elif itemType == FunctionItemType:
                if not isinstance(info, list):
                    info = info.functions
            elif itemType == DecoratorItemType:
                info = info.decorators
            found = False
            for item in info:
                if item.getDisplayName() == pathItem:
                    found = True
                    info = item
                    break
            if found:
                continue
            return None
    return info
