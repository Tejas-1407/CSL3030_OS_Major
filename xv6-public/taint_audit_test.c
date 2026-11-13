#include "types.h"
#include "stat.h"
#include "fcntl.h"
#include "user.h"

#define TAINT_DATA "taintdata"
#define TAINT_EXEC "taint_exec"
#define TAINT_READ_TARGET "taint_read_target"
#define TAINT_EXEC_TARGET "taint_exec_target"

static int
remove_if_present(char *path)
{
  int fd;

  if((fd = open(path, O_RDONLY)) < 0)
    return 0;
  close(fd);
  return unlink(path);
}

static int
create_target(char *path)
{
  int fd;
  char contents[] = "temporary unlink target\n";

  if((fd = open(path, O_CREATE|O_RDWR)) < 0)
    return -1;
  if(write(fd, contents, sizeof(contents)-1) != sizeof(contents)-1){
    close(fd);
    return -1;
  }
  close(fd);
  return 0;
}

static void
make_tainted_files(void)
{
  int source, data, executable;
  int n;
  char byte;
  char buffer[512];
  char data_contents[] = "written by an inbox-tainted process\n";

  if((source = open("inbox.txt", O_RDONLY)) < 0 ||
     read(source, &byte, 1) != 1){
    printf(1, "TAINT_AUDIT FAIL maker inbox read\n");
    exit();
  }
  close(source);

  if((data = open(TAINT_DATA, O_CREATE|O_RDWR)) < 0 ||
     write(data, data_contents, sizeof(data_contents)-1) !=
       sizeof(data_contents)-1){
    printf(1, "TAINT_AUDIT FAIL tainted data write\n");
    exit();
  }
  close(data);
  printf(1, "TAINT_AUDIT PASS tainted_regular_file_write\n");

  if((source = open("taint_probe", O_RDONLY)) < 0 ||
     (executable = open(TAINT_EXEC, O_CREATE|O_RDWR)) < 0){
    printf(1, "TAINT_AUDIT FAIL executable copy open\n");
    exit();
  }
  while((n = read(source, buffer, sizeof(buffer))) > 0){
    if(write(executable, buffer, n) != n){
      printf(1, "TAINT_AUDIT FAIL executable copy write\n");
      close(source);
      close(executable);
      exit();
    }
  }
  close(source);
  close(executable);
  if(n < 0){
    printf(1, "TAINT_AUDIT FAIL executable copy read\n");
    exit();
  }
  printf(1, "TAINT_AUDIT PASS tainted_executable_created\n");
  exit();
}

static void
wait_for_release(int fd)
{
  char token;

  if(read(fd, &token, 1) != 1){
    printf(1, "TAINT_AUDIT FAIL release synchronization\n");
    exit();
  }
  close(fd);
}

int
main(void)
{
  int read_gate[2], exec_gate[2];
  int read_child, exec_child, maker;
  char token;
  char *read_argv[] = {"taint_probe", "read", 0};
  char *exec_argv[] = {TAINT_EXEC, "exec", 0};

  remove_if_present(TAINT_DATA);
  remove_if_present(TAINT_EXEC);
  remove_if_present(TAINT_READ_TARGET);
  remove_if_present(TAINT_EXEC_TARGET);
  if(create_target(TAINT_READ_TARGET) < 0 ||
     create_target(TAINT_EXEC_TARGET) < 0){
    printf(1, "TAINT_AUDIT FAIL create target\n");
    exit();
  }
  if(pipe(read_gate) < 0 || pipe(exec_gate) < 0){
    printf(1, "TAINT_AUDIT FAIL synchronization pipes\n");
    exit();
  }

  read_child = fork();
  if(read_child < 0){
    printf(1, "TAINT_AUDIT FAIL fork read probe\n");
    exit();
  }
  if(read_child == 0){
    close(read_gate[1]);
    close(exec_gate[0]);
    close(exec_gate[1]);
    wait_for_release(read_gate[0]);
    exec("taint_probe", read_argv);
    printf(1, "TAINT_AUDIT FAIL start read probe\n");
    exit();
  }

  exec_child = fork();
  if(exec_child < 0){
    printf(1, "TAINT_AUDIT FAIL fork exec probe\n");
    exit();
  }
  if(exec_child == 0){
    close(exec_gate[1]);
    close(read_gate[0]);
    close(read_gate[1]);
    wait_for_release(exec_gate[0]);
    exec(TAINT_EXEC, exec_argv);
    printf(1, "TAINT_AUDIT FAIL start tainted executable\n");
    exit();
  }

  close(read_gate[0]);
  close(exec_gate[0]);
  maker = fork();
  if(maker < 0){
    printf(1, "TAINT_AUDIT FAIL fork tainted writer\n");
    exit();
  }
  if(maker == 0){
    close(read_gate[1]);
    close(exec_gate[1]);
    make_tainted_files();
  }

  wait();
  token = 'r';
  if(write(read_gate[1], &token, 1) != 1){
    printf(1, "TAINT_AUDIT FAIL release read probe\n");
    exit();
  }
  close(read_gate[1]);
  wait();

  token = 'e';
  if(write(exec_gate[1], &token, 1) != 1){
    printf(1, "TAINT_AUDIT FAIL release exec probe\n");
    exit();
  }
  close(exec_gate[1]);
  wait();

  if(remove_if_present(TAINT_DATA) < 0 ||
     remove_if_present(TAINT_EXEC) < 0 ||
     remove_if_present(TAINT_READ_TARGET) < 0 ||
     remove_if_present(TAINT_EXEC_TARGET) < 0){
    printf(1, "TAINT_AUDIT FAIL clean temporary files\n");
    exit();
  }
  printf(1, "TAINT_AUDIT COMPLETE temporary_files=clean\n");
  exit();
}
