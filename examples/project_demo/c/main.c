#include <stdio.h>
#include "include/math_ops.h"

int main(void) {
    const int values[] = {2, 3, 5};
    printf("C: sample = %d\n", calculate_total(values, 3));
    return 0;
}
