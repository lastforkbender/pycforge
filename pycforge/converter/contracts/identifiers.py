"""Data-only ISO C11 identifier reservations shared by planning and validation."""

from __future__ import annotations


C_KEYWORDS = frozenset({
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if",
    "inline", "int", "long", "register", "restrict", "return", "short",
    "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
    "unsigned", "void", "volatile", "while", "_Alignas", "_Alignof",
    "_Atomic", "_Bool", "_Complex", "_Generic", "_Imaginary", "_Noreturn",
    "_Static_assert", "_Thread_local",
})

TARGET_RESERVED_NAMES = {
    "bool", "true", "false", "size_t",
    "int8_t", "uint8_t", "int16_t", "uint16_t", "int32_t", "uint32_t",
    "int64_t", "uint64_t",
}
for _width in (8, 16, 32, 64):
    TARGET_RESERVED_NAMES.update({
        f"int_least{_width}_t", f"uint_least{_width}_t", f"int_fast{_width}_t", f"uint_fast{_width}_t",
        f"INT{_width}_MIN", f"INT{_width}_MAX", f"UINT{_width}_MAX", f"INT{_width}_C", f"UINT{_width}_C",
        f"INT_LEAST{_width}_MIN", f"INT_LEAST{_width}_MAX", f"UINT_LEAST{_width}_MAX",
        f"INT_FAST{_width}_MIN", f"INT_FAST{_width}_MAX", f"UINT_FAST{_width}_MAX",
    })
TARGET_RESERVED_NAMES.update({
    "intptr_t", "uintptr_t", "intmax_t", "uintmax_t", "INTPTR_MIN", "INTPTR_MAX", "UINTPTR_MAX",
    "INTMAX_MIN", "INTMAX_MAX", "UINTMAX_MAX", "INTMAX_C", "UINTMAX_C", "PTRDIFF_MIN", "PTRDIFF_MAX",
    "SIG_ATOMIC_MIN", "SIG_ATOMIC_MAX", "SIZE_MAX", "WCHAR_MIN", "WCHAR_MAX", "WINT_MIN", "WINT_MAX",
})
TARGET_RESERVED_NAMES = frozenset(TARGET_RESERVED_NAMES)

# ISO C library identifiers with external linkage are reserved even when their
# declaring header is not included. `main` is included as the hosted entry point.
C11_EXTERNAL_IDENTIFIERS = frozenset("""
main errno stdin stdout stderr
isalnum isalpha isblank iscntrl isdigit isgraph islower isprint ispunct isspace isupper isxdigit tolower toupper
feclearexcept fegetexceptflag feraiseexcept fesetexceptflag fetestexcept fegetround fesetround fegetenv feholdexcept fesetenv feupdateenv
imaxabs imaxdiv strtoimax strtoumax wcstoimax wcstoumax setlocale localeconv setjmp longjmp signal raise
remove rename tmpfile tmpnam fclose fflush fopen freopen setbuf setvbuf fprintf fscanf printf scanf snprintf sprintf sscanf
vfprintf vfscanf vprintf vscanf vsnprintf vsprintf vsscanf fgetc fgets fputc fputs getc getchar putc putchar puts ungetc
fread fwrite fgetpos fseek fsetpos ftell rewind clearerr feof ferror perror
atof atoi atol atoll strtod strtof strtold strtol strtoll strtoul strtoull rand srand aligned_alloc calloc free malloc realloc
abort atexit at_quick_exit exit _Exit getenv quick_exit system bsearch qsort abs labs llabs div ldiv lldiv
mblen mbtowc wctomb mbstowcs wcstombs
memcpy memmove strcpy strncpy strcat strncat memcmp strcmp strcoll strncmp strxfrm memchr strchr strcspn strpbrk strrchr strspn strstr strtok memset strerror strlen
call_once cnd_broadcast cnd_destroy cnd_init cnd_signal cnd_timedwait cnd_wait mtx_destroy mtx_init mtx_lock mtx_timedlock mtx_trylock mtx_unlock
thrd_create thrd_current thrd_detach thrd_equal thrd_exit thrd_join thrd_sleep thrd_yield tss_create tss_delete tss_get tss_set
clock difftime mktime time timespec_get asctime ctime gmtime localtime strftime
mbrtoc16 c16rtomb mbrtoc32 c32rtomb
fwprintf fwscanf swprintf swscanf vfwprintf vfwscanf vswprintf vswscanf vwprintf vwscanf wprintf wscanf
fgetwc fgetws fputwc fputws fwide getwc getwchar putwc putwchar ungetwc
wcstod wcstof wcstold wcstol wcstoll wcstoul wcstoull wcscpy wcsncpy wmemcpy wmemmove wcscat wcsncat
wmemcmp wcscmp wcscoll wcsncmp wcsxfrm wmemchr wcschr wcscspn wcspbrk wcsrchr wcsspn wcsstr wcstok wmemset wcslen wcsftime
btowc wctob mbsinit mbrlen mbrtowc wcrtomb mbsrtowcs wcsrtombs
iswalnum iswalpha iswblank iswcntrl iswctype iswdigit iswgraph iswlower iswprint iswpunct iswspace iswupper iswxdigit towlower towupper towctrans wctype wctrans
""".split())

_MATH_EXTERNAL_BASES = frozenset("""
acos asin atan atan2 cos sin tan acosh asinh atanh exp exp2 expm1 frexp ilogb ldexp log log10 log1p log2 logb modf scalbn scalbln
cbrt fabs hypot pow sqrt erf erfc lgamma tgamma ceil floor nearbyint rint lrint llrint round lround llround trunc
fmod remainder remquo copysign nan nextafter nexttoward fdim fmax fmin fma
cacos casin catan ccos csin ctan cacosh casinh catanh cexp clog cabs cpow csqrt carg cimag conj cproj creal
""".split())
C11_EXTERNAL_IDENTIFIERS |= frozenset(name + suffix for name in _MATH_EXTERNAL_BASES for suffix in ("", "f", "l"))

