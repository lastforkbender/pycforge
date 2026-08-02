#include <stdint.h>

static int64_t pycf_i64_floor_div_v1(int64_t pycf_dividend, int64_t pycf_divisor);

static int64_t pycf_i64_floor_div_v1(int64_t pycf_dividend, int64_t pycf_divisor)
{
    int64_t pycf_quotient = pycf_dividend / pycf_divisor;
    int64_t pycf_remainder = pycf_dividend % pycf_divisor;
    if (pycf_remainder != 0LL && pycf_remainder < 0LL != pycf_divisor < 0LL)
    {
        pycf_quotient = pycf_quotient - 1LL;
    }
    return pycf_quotient;
}
