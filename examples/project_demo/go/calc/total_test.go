package calc

import "testing"

func TestTotal(t *testing.T) {
	actual := Total([]int{2, 3, 5}, 2)
	if actual != 20 {
		t.Fatalf("unexpected total: %d", actual)
	}
}
