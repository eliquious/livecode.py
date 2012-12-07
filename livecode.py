import sublime, sublime_plugin, os, glob, sys
import ast, time, default_completions
from smash import Tree

def getmodules():
    modules = []
    for path in sys.path:
        try:
            files = os.listdir(path)
            for fn in files:
                if fn.endswith("py"):
                    name = fn.replace(".py", "")
                    modules.append((name + "\tmodule", name,))
                elif os.path.isdir(fn):
                    if "__init__.py" in os.listdir(fn):
                        modules.append((fn + "\tmodule", fn,))
        except:
            pass

    for module in default_completions.stdlib:
        modules.append((module["trigger"], module["content"],))
    return set(modules)

class ImportVisitor(ast.NodeVisitor):
    """docstring for ImportVisitor"""
    def __init__(self):
        super(ImportVisitor, self).__init__()
        self.names = []
        self.nodes = []

    def visit_Import(self, node):
        for name in node.names:
            self.names.append((name.name, None,))
        self.nodes.append(node)

    def visit_ImportFrom(self, node):
        for name in node.names:
            self.names.append((node.module, name.name,))
        self.nodes.append(node)

class VariableVisitor(ast.NodeVisitor):
    """docstring for VariableVisitor"""
    def __init__(self):
        super(VariableVisitor, self).__init__()
        self.names = []
        self.nodes = []

    def visit_Name(self, node):
        if node.ctx.__class__.__name__ in ["Store", "Param"]:
            if "self" not in node.id:
                self.names.append(node.id)
                self.nodes.append(node)

class InstanceVariableVisitor(ast.NodeVisitor):
    """docstring for InstanceVariableVisitor"""
    def __init__(self):
        super(InstanceVariableVisitor, self).__init__()
        self.names = []
        self.nodes = []

    def visit_Assign(self, node):
        for target in node.targets:
            if hasattr(target, "value"):
                if target.value.id == "self":
                    self.names.append(target.attr)
                    self.nodes.append(target)

class ClassDefVisitor(ast.NodeVisitor):
    """docstring for ClassDefVisitor"""
    def __init__(self):
        super(ClassDefVisitor, self).__init__()
        self.names = []
        self.nodes = []

    def visit_ClassDef(self, node):
        self.names.append(node.name)
        self.nodes.append(node)

class FunctionDefVisitor(ast.NodeVisitor):
    """docstring for FunctionDefVisitor"""
    def __init__(self):
        super(FunctionDefVisitor, self).__init__()
        self.names = []
        self.nodes = []

    def visit_FunctionDef(self, node):
        self.names.append(node.name)
        self.nodes.append(node)

class AST(Tree):
    """docstring for AST"""
    def __init__(self, code):
        super(AST, self).__init__(names=["lineno", "col_offset", "node"])
        self.source = ast.parse(code)
        for lineno, col_offset, node in self._nodes(self.source):
            self.put(lineno=lineno, col_offset=col_offset, node=node)

    def __getattr__(self, attr):
        if attr.startswith("get") and len(attr) > 3:
            return lambda: self.query(filters={"node": lambda node: attr[3:] == node.__class__.__name__})
        return self.__dict__[attr]
    #     super(AST, self).__getattr__(self, attr)

    def _nodes(self, root):
        for node in ast.iter_child_nodes(root):
            lineno = node.lineno if hasattr(node, "lineno") else None
            col_offset = node.col_offset if hasattr(node, "col_offset") else None

            if lineno is not None and col_offset is not None:
                yield lineno, col_offset, node

            for n in self._nodes(node):
                yield n

    def rootnodes(self):
        return ast.iter_child_nodes(self.source)

    def context(self, lineno, root=None):
        if root is None:
            root = self.source
        if "body" in root._fields:
            # print "" * depth, root
            yield root

            inside = None
            for child in ast.iter_child_nodes(root):
                if hasattr(child, "lineno"):
                    if child.lineno > lineno:
                        break
                    inside = child
            if inside is not None:
                for inner in self.context(lineno, root=inside):
                    yield inner

    def instancevariables(self, node=None):
        if node is None:
            node = self.source
        v = InstanceVariableVisitor()
        v.visit(node)
        return set(v.names)

    def variables(self, node=None):
        if node is None:
            node = self.source
        v = VariableVisitor()
        v.visit(node)
        return set(v.names)

    def functions(self, node=None):
        if node is None:
            node = self.source
        v = FunctionDefVisitor()
        v.visit(node)
        return set(v.names)

    def classes(self, node=None):
        if node is None:
            node = self.source
        v = ClassDefVisitor()
        v.visit(node)
        return set(v.names)

    def imports(self, node=None, lineno=0):
        imports = []
        if lineno > 0:
            containers = list(self.context(lineno))
            containers.reverse()
            for container in containers:
                if "Module" not in container.__class__.__name__:
#                imports.extend(self.imports(container))
                    v = ImportVisitor()
                    v.visit(container)
                    for iname in v.nodes:
                        if iname.lineno <= lineno:
                            if "ImportFrom" in iname.__class__.__name__:
                                for child in iname.names:
                                    imports.append((node.module, child.name,))
                            elif "Import" in iname.__class__.__name__:
                                for child in iname.names:
                                    imports.append((child.name, None,))
                else:
                    for node in self.rootnodes():
                        if "ImportFrom" in node.__class__.__name__:
                            for child in node.names:
                                imports.append((node.module, child.name,))
                        elif "Import" in node.__class__.__name__:
                            for child in node.names:
                                imports.append((child.name, None,))
                # imports.extend(self.getImport())
                # imports.extend(self.getImportFrom())
        elif node is not None and hasattr(node, "lineno"):
            for container in self.context(lineno, node):
                imports.extend(self.imports(container))
        else:
            v = ImportVisitor()
            v.visit(self.source)
            imports.extend(v.names)
        return set(imports)

    def isFunction(self, name):
        pass

    def isImport(self, name):
        pass

    def isClass(self, name):
        pass

class LiveCode(sublime_plugin.EventListener):

    def getsubregion(self, view, prefix, locations, size):
        loc = locations[0] - len(prefix) - size
        string = view.substr(sublime.Region(loc, loc + size))
        return string

    def isself(self, view, prefix, locations):
        string = self.getsubregion(view, prefix, locations, 5)
        return "self" in string

    def isimport(self, view, prefix, locations):
        string = self.getsubregion(view, prefix, locations, 80)
        return "import" in string or "from" in string

    def isperiod(self, view, prefix, locations):
        string = self.getsubregion(view, prefix, locations, 1)
        return "." in string

    def ivariables(self, row):
        opts = set([])
        for ctx in self.source.context(row):
            if not "Module" in ctx.__class__.__name__:
                ivars = self.source.instancevariables(ctx)
                opts.update(ivars)
        return opts

    def variables(self, lineno):
        opts = set([])
        containers = list(self.source.context(lineno))
        containers.reverse()
        for ctx in containers:
            if "body" in ctx._fields:
                for root in ast.iter_child_nodes(ctx):
                    if "Name" in root.__class__.__name__:
                        if hasattr(root, "id"):
                            opts.add(root.id)
                    elif "Assign" in root.__class__.__name__:
                        for target in root.targets:
                            if hasattr(target, "id"):
                                opts.add(target.id)
        return opts

    def arguments(self, lineno):
        opts = set([])
        containers = list(self.source.context(lineno))
        containers.reverse()
        for ctx in containers:
            if "args" in ctx._fields:
                if ctx.args.args is not None:
                    for arg in ctx.args.args:
                        opts.add(arg.id)
        return opts

    def kwarguments(self, lineno):
        opts = set([])
        containers = list(self.source.context(lineno))
        containers.reverse()
        for ctx in containers:
            if "args" in ctx._fields:
                if ctx.args.kwarg is not None:
                    for kwarg in container.args.kwarg:
                        opts.add(kwarg.id)
        return opts

    def functions(self, lineno):
        return self.source.functions()

    def classes(self, lineno):
        return self.source.classes()

    def on_query_completions(self, view, prefix, locations):
        # global py_funcs, py_members, subl_methods, subl_methods_all
        print "on_query_completions"
        if not view.match_selector(locations[0], 'source.python'): #  -string -comment -constant
            print "exiting"
            return []

        completions = []
        compl_full = []
        row, col = view.rowcol(locations[0])
        if hasattr(self, "source") and self.source is not None:
            if self.isself(view, prefix, locations):

                # instance variables
                ivars = self.ivariables(row)
                for var in ivars:
                    completions.append((var + "\tinst var", var,))

                # functions
                vars = self.functions(row)
                for var in vars:
                    completions.append((var + "\tfunc def", var,))

                # classes
                vars = self.classes(row)
                for var in vars:
                    completions.append((var + "\tclass def", var,))
            else:

                if self.isimport(view, prefix, locations):
                    # imports
                    vars = self.source.imports(lineno=row)
                    for module, alias in vars:
                        if alias is not None:
                            completions.append((alias + "\timport", alias,))
                        completions.append((module + "\tmodule", module,))

                    if not hasattr(self, "peer_modules") or time.time() - self.last_modified > 0.3:
                        self.peer_modules = getmodules()

                    # add modules
                    completions.extend(self.peer_modules)

                # variables
                vars = self.variables(row)
                for var in vars:
                    completions.append((var + "\tvar", var,))

                # arguments
                vars = self.arguments(row)
                for var in vars:
                    completions.append((var + "\targ", var,))

                # keyword arguments
                vars = self.kwarguments(row)
                for var in vars:
                    completions.append((var + "\tkwarg", var,))

                # functions
                vars = self.functions(row)
                for var in vars:
                    completions.append((var + "\tfunc def", var,))

                # classes
                vars = self.classes(row)
                for var in vars:
                    completions.append((var + "\tclass def", var,))

        # default completions
        # compl_default = [view.extract_completions(prefix)]
        # compl_default = [(item + "\tDefault", item) for sublist in compl_default
        #     for item in sublist if len(item) > 3]       # flatten
        # compl_default = list(set(compl_default))        # make unique
        # compl_default.sort()
        # compl_full.extend(completions)
        # compl_full = set(compl_full)
        # compl_full.sort()

        return (completions, 0) # sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_EXPLICIT_COMPLETIONS

    def on_modified(self, view):
        # print "View Modified"
        init = False
        if not hasattr(self, "last_modified"):
            self.last_modified = time.time()
            init = True

        if init or time.time() - self.last_modified > 0.25:
            code = None
            try:
                code = AST(view.substr(sublime.Region(0, view.size())))
            except:
                pass
            finally:
                if code is not None:
                    self.source = code
                self.last_modified = time.time()


