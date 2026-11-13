#include "types.h"
#include "stat.h"
#include "fcntl.h"
#include "user.h"

int
main(int argc, char *argv[])
{
  int fd;
  char byte;
  int n;
  char *target;

  if(argc != 2){
    printf(1, "TAINT_AUDIT FAIL probe arguments\n");
    exit();
  }

  if(strcmp(argv[1], "read") == 0)
    target = "taint_read_target";
  else if(strcmp(argv[1], "exec") == 0)
    target = "taint_exec_target";
  else {
    printf(1, "TAINT_AUDIT FAIL unknown probe mode\n");
    exit();
  }

  if((fd = open(target, O_RDONLY)) < 0){
    printf(1, "TAINT_AUDIT FAIL target missing\n");
    exit();
  }
  n = read(fd, &byte, 1);
  close(fd);
  if(n != 1){
    printf(1, "TAINT_AUDIT FAIL target unreadable\n");
    exit();
  }

  if(strcmp(argv[1], "read") == 0){
    if((fd = open("taintdata", O_RDONLY)) < 0){
      printf(1, "TAINT_AUDIT FAIL tainted data missing\n");
      exit();
    }
    n = read(fd, &byte, 1);
    close(fd);
    if(n != 1){
      printf(1, "TAINT_AUDIT FAIL tainted data unreadable\n");
      exit();
    }
    if(unlink(target) == 0){
      printf(1, "TAINT_AUDIT FAIL tainted file read did not block unlink\n");
      exit();
    }
    printf(1, "TAINT_AUDIT PASS tainted_file_read unlink_denied\n");
  } else {
    if(unlink(target) == 0){
      printf(1, "TAINT_AUDIT FAIL tainted exec did not block unlink\n");
      exit();
    }
    printf(1, "TAINT_AUDIT PASS tainted_exec unlink_denied\n");
  }
  exit();
}
