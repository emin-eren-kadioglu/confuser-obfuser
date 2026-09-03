package calc

func Total(values []int, multiplier int) int {
	subtotal := 0
	for _, value := range values {
		subtotal += value
	}
	return subtotal * multiplier
}
