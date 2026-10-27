#include "types.h"
#include "stat.h"
#include "user.h"

int
main(int argc, char *argv[])
{
  int a = 10;
  int b = 25;
  int r = add(a, b);

  printf(1, "add(%d, %d) = %d\n", a, b, r);
  exit();
}
