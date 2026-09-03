#include "include/math_ops.h"

int calculate_total(const int *values, int count) {
    int subtotal = 0;
    for (int index = 0; index < count; ++index) {
        subtotal += values[index];
    }
    return subtotal * PROJECT_FACTOR;
}
