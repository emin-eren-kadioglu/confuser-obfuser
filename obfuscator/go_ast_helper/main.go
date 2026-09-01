// Confuser Obfuser Go AST helper. It intentionally uses only the Go standard library.
package main

import (
	"encoding/json"
	"fmt"
	"go/ast"
	"go/build"
	"go/format"
	"go/importer"
	"go/parser"
	"go/token"
	"go/types"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type request struct {
	Source   string `json:"source"`
	Filename string `json:"filename"`
	Seed     uint64 `json:"seed"`
}

type generator struct {
	state uint64
	used  map[string]bool
}

func (g *generator) next() uint64 {
	if g.state == 0 {
		g.state = 0x9e3779b97f4a7c15
	}
	x := g.state
	x ^= x << 13
	x ^= x >> 7
	x ^= x << 17
	g.state = x
	return x
}

func (g *generator) name() string {
	const alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
	for {
		value := "_cf_"
		for index := 0; index < 9; index++ {
			value += string(alphabet[g.next()%uint64(len(alphabet))])
		}
		if !g.used[value] {
			g.used[value] = true
			return value
		}
	}
}

func sameFile(fileset *token.FileSet, identifier *ast.Ident, filename string) bool {
	position := fileset.Position(identifier.Pos())
	actual, error := filepath.Abs(position.Filename)
	if error != nil {
		return filepath.Clean(position.Filename) == filepath.Clean(filename)
	}
	expected, error := filepath.Abs(filename)
	if error != nil {
		return filepath.Clean(actual) == filepath.Clean(filename)
	}
	return filepath.Clean(actual) == filepath.Clean(expected)
}

func loadPackage(fileset *token.FileSet, input request) (*ast.File, []*ast.File, error) {
	target, error := parser.ParseFile(fileset, input.Filename, input.Source, parser.ParseComments)
	if error != nil {
		return nil, nil, error
	}
	files := []*ast.File{target}
	directory := filepath.Dir(input.Filename)
	entries, readError := os.ReadDir(directory)
	if readError != nil {
		return target, files, nil
	}
	targetPath, _ := filepath.Abs(input.Filename)
	for _, entry := range entries {
		name := entry.Name()
		if entry.IsDir() || !strings.HasSuffix(name, ".go") || strings.HasSuffix(name, "_test.go") || strings.Contains(name, ".obf.go") {
			continue
		}
		candidatePath, _ := filepath.Abs(filepath.Join(directory, name))
		if filepath.Clean(candidatePath) == filepath.Clean(targetPath) {
			continue
		}
		matches, matchError := build.Default.MatchFile(directory, name)
		if matchError != nil || !matches {
			continue
		}
		candidate, parseError := parser.ParseFile(fileset, candidatePath, nil, parser.ParseComments)
		if parseError == nil && candidate.Name.Name == target.Name.Name {
			files = append(files, candidate)
		}
	}
	return target, files, nil
}

func transform(input request) ([]byte, error) {
	fileset := token.NewFileSet()
	target, files, loadError := loadPackage(fileset, input)
	if loadError != nil {
		return nil, loadError
	}
	information := &types.Info{
		Defs: make(map[*ast.Ident]types.Object),
		Uses: make(map[*ast.Ident]types.Object),
	}
	var typeErrors []error
	configuration := types.Config{
		Importer: importer.Default(),
		Error: func(problem error) {
			typeErrors = append(typeErrors, problem)
		},
	}
	checkedPackage, checkError := configuration.Check(target.Name.Name, fileset, files, information)
	if checkError != nil {
		if len(typeErrors) > 0 {
			return nil, fmt.Errorf("type checking failed: %w", typeErrors[0])
		}
		return nil, fmt.Errorf("type checking failed: %w", checkError)
	}

	used := make(map[string]bool)
	for _, file := range files {
		ast.Inspect(file, func(node ast.Node) bool {
			if identifier, ok := node.(*ast.Ident); ok {
				used[identifier.Name] = true
			}
			return true
		})
	}
	generator := generator{state: input.Seed, used: used}

	definitions := make([]*ast.Ident, 0)
	for identifier, object := range information.Defs {
		if object != nil && sameFile(fileset, identifier, input.Filename) {
			definitions = append(definitions, identifier)
		}
	}
	sort.Slice(definitions, func(left, right int) bool {
		return definitions[left].Pos() < definitions[right].Pos()
	})

	externalUse := make(map[types.Object]bool)
	for identifier, object := range information.Uses {
		if object != nil && !sameFile(fileset, identifier, input.Filename) {
			externalUse[object] = true
		}
	}

	renames := make(map[types.Object]string)
	for _, identifier := range definitions {
		object := information.Defs[identifier]
		if object == nil || object.Name() == "_" || externalUse[object] {
			continue
		}
		switch value := object.(type) {
		case *types.Func:
			signature, ok := value.Type().(*types.Signature)
			if !ok || signature.Recv() != nil || value.Name() == "main" || value.Name() == "init" {
				continue
			}
		case *types.Var:
			if value.IsField() || value.Parent() == checkedPackage.Scope() {
				continue
			}
		default:
			continue
		}
		renames[object] = generator.name()
	}

	for identifier, object := range information.Defs {
		if replacement, ok := renames[object]; ok && sameFile(fileset, identifier, input.Filename) {
			identifier.Name = replacement
		}
	}
	for identifier, object := range information.Uses {
		if replacement, ok := renames[object]; ok && sameFile(fileset, identifier, input.Filename) {
			identifier.Name = replacement
		}
	}
	return format.Source([]byte(nodeString(fileset, target)))
}

func nodeString(fileset *token.FileSet, node ast.Node) string {
	var builder strings.Builder
	if error := format.Node(&builder, fileset, node); error != nil {
		panic(error)
	}
	return builder.String()
}

func main() {
	var input request
	if error := json.NewDecoder(os.Stdin).Decode(&input); error != nil {
		fmt.Fprintln(os.Stderr, error)
		os.Exit(2)
	}
	result, error := transform(input)
	if error != nil {
		fmt.Fprintln(os.Stderr, error)
		os.Exit(2)
	}
	if _, error := os.Stdout.Write(result); error != nil {
		fmt.Fprintln(os.Stderr, error)
		os.Exit(2)
	}
}
