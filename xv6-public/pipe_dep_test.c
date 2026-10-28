#include "types.h"
#include "stat.h"
#include "user.h"

int
main(int argc, char *argv[])
{
  int datafd[2];
  int syncfd[2];
  int pid;
  char first, second, ready;

  if(pipe(datafd) < 0 || pipe(syncfd) < 0){
    printf(1, "pipe_dep_test: pipe creation failed\n");
    exit();
  }

  pid = fork();
  if(pid < 0){
    printf(1, "pipe_dep_test: fork failed\n");
    exit();
  }
  if(pid == 0){
    close(datafd[1]);
    close(syncfd[0]);

    if(read(datafd[0], &first, 1) != 1){
      printf(1, "pipe_dep_test: child first read failed\n");
      exit();
    }
    ready = 'r';
    if(write(syncfd[1], &ready, 1) != 1){
      printf(1, "pipe_dep_test: child notification failed\n");
      exit();
    }

    if(read(datafd[0], &second, 1) == 1)
      printf(1, "pipe_dep_test: success, read %c then %c\n",
             first, second);
    else
      printf(1, "pipe_dep_test: child second read failed\n");

    close(datafd[0]);
    close(syncfd[1]);
    exit();
  }

  close(datafd[0]);
  close(syncfd[1]);

  first = 'A';
  if(write(datafd[1], &first, 1) != 1){
    printf(1, "pipe_dep_test: parent first write failed\n");
    exit();
  }
  if(read(syncfd[0], &ready, 1) != 1){
    printf(1, "pipe_dep_test: parent notification read failed\n");
    exit();
  }

  sleep(2);
  second = 'B';
  if(write(datafd[1], &second, 1) != 1)
    printf(1, "pipe_dep_test: parent second write failed\n");

  close(datafd[1]);
  close(syncfd[0]);
  wait();
  exit();
}
