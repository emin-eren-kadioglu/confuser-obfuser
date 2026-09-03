package main

import (
	"fmt"
	"strings"

	"example.com/confuser-demo/calc"
)

func main() {
	values := []int{2, 3, 5}
	fmt.Printf("Go: %s = %d\n", strings.TrimSpace(banner), calc.Total(values, 2))
}
