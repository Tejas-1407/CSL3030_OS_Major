#include "types.h"
#include "stat.h"
#include "fcntl.h"
#include "user.h"

static int
read_one_byte(char *path)
{
  int fd;
  char byte;
  int n;

  if((fd = open(path, O_RDONLY)) < 0)
    return -1;
  n = read(fd, &byte, 1);
  close(fd);
  return n;
}

int
main(void)
{
  int fd;
  int report[2];
  int child;
  char byte;
  char sentinel[] =
    "SAFE SENTINEL: this guest file must remain unchanged during the demonstration.\n";

  if(read_one_byte("README") != 1){
    printf(1, "TAINT_TEST FAIL trusted file read\n");
    exit();
  }
  if((fd = open("taint-cleanup.tmp", O_CREATE|O_RDWR)) < 0){
    printf(1, "TAINT_TEST FAIL create trusted cleanup file\n");
    exit();
  }
  close(fd);
  if(unlink("taint-cleanup.tmp") < 0){
    printf(1, "TAINT_TEST FAIL untainted unlink denied\n");
    exit();
  }
  printf(1, "TAINT_TEST PASS trusted_read=clean untainted_unlink=allowed\n");

  if(pipe(report) < 0){
    printf(1, "TAINT_TEST FAIL report pipe creation\n");
    exit();
  }
  child = fork();
  if(child < 0){
    printf(1, "TAINT_TEST FAIL fork tainted reader\n");
    exit();
  }
  if(child == 0){
    close(report[0]);
    if(read_one_byte("inbox.txt") != 1){
      printf(1, "TAINT_TEST FAIL inbox read\n");
      byte = 'E';
      write(report[1], &byte, 1);
      exit();
    }

    child = fork();
    if(child < 0){
      printf(1, "TAINT_TEST FAIL fork taint inheritance\n");
      byte = 'E';
      write(report[1], &byte, 1);
      exit();
    }
    if(child == 0){
      if(unlink("important.txt") == 0){
        printf(1, "TAINT_TEST FAIL forked taint did not deny unlink\n");
        if((fd = open("important.txt", O_CREATE|O_RDWR)) >= 0){
          write(fd, sentinel, sizeof(sentinel)-1);
          close(fd);
        }
        byte = 'E';
      } else {
        printf(1, "TAINT_TEST PASS fork_inherits_taint unlink=denied\n");
        byte = 'F';
      }
      if(write(report[1], &byte, 1) != 1)
        printf(1, "TAINT_TEST FAIL report fork result\n");
      exit();
    }
    wait();
    close(report[1]);
    exit();
  }

  close(report[1]);
  if(read(report[0], &byte, 1) != 1){
    printf(1, "TAINT_TEST FAIL missing fork report\n");
    exit();
  }
  wait();
  close(report[0]);
  if(byte != 'F'){
    printf(1, "TAINT_TEST FAIL fork taint enforcement\n");
    exit();
  }

  // The report pipe was written by a tainted child, so this read taints us.
  if(unlink("important.txt") == 0){
    printf(1, "TAINT_TEST FAIL pipe taint did not deny unlink\n");
    if((fd = open("important.txt", O_CREATE|O_RDWR)) >= 0){
      write(fd, sentinel, sizeof(sentinel)-1);
      close(fd);
    }
    exit();
  }
  if(read_one_byte("important.txt") != 1){
    printf(1, "TAINT_TEST FAIL protected file missing\n");
    exit();
  }
  printf(1, "TAINT_TEST PASS pipe_propagates_taint unlink=denied sentinel=present\n");
  printf(1, "TAINT_TEST COMPLETE\n");
  exit();
}
