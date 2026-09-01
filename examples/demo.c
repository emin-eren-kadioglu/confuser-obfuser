#include <stdio.h>

int add(int left, int right) {
    int total = left + right;
    return total;
}

int main(void) {
    printf("Result: %d", add(2, 5));
    putchar('\n');
    return 0;
}
