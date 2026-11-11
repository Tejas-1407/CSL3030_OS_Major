#include "types.h"
#include "stat.h"
#include "user.h"

int
main(int argc, char *argv[])
{
  int data_a[2], data_c[2];
  int ready[2], writer_go[2], competitor_go[2], ack_a[2];
  int pid, i;
  char token, prime, second;

  if(pipe(data_a) < 0 || pipe(data_c) < 0 ||
     pipe(ready) < 0 || pipe(writer_go) < 0 ||
     pipe(competitor_go) < 0 || pipe(ack_a) < 0){
    printf(1, "donation_multi_test: pipe creation failed\n");
    exit();
  }

  pid = fork();
  if(pid < 0){
    printf(1, "donation_multi_test: fork writer failed\n");
    exit();
  }
  if(pid == 0){
    close(data_a[0]);
    close(data_c[0]);
    close(ready[0]);
    close(ready[1]);
    close(writer_go[1]);
    close(competitor_go[0]);
    close(competitor_go[1]);
    close(ack_a[1]);
    if(setworkflow(1, 300) < 0)
      exit();

    prime = 'a';
    if(write(data_a[1], &prime, 1) != 1)
      exit();
    prime = 'c';
    if(write(data_c[1], &prime, 1) != 1)
      exit();
    if(read(writer_go[0], &token, 1) != 1)
      exit();

    second = 'A';
    if(write(data_a[1], &second, 1) != 1)
      exit();
    if(read(ack_a[0], &token, 1) != 1)
      exit();

    printf(1, "WRITER_AFTER_A pid=%d\n", getpid());
    close(data_a[1]);
    close(data_c[1]);
    close(writer_go[0]);
    close(ack_a[0]);
    exit();
  }

  pid = fork();
  if(pid < 0){
    printf(1, "donation_multi_test: fork reader A failed\n");
    exit();
  }
  if(pid == 0){
    close(data_a[1]);
    close(data_c[0]);
    close(data_c[1]);
    close(ready[0]);
    close(writer_go[0]);
    close(writer_go[1]);
    close(competitor_go[0]);
    close(competitor_go[1]);
    close(ack_a[0]);
    if(setworkflow(2, 100) < 0)
      exit();

    if(read(data_a[0], &prime, 1) != 1)
      exit();
    token = 'a';
    if(write(ready[1], &token, 1) != 1)
      exit();
    if(read(data_a[0], &second, 1) != 1)
      exit();
    printf(1, "READER_A_EXIT pid=%d\n", getpid());
    if(write(ack_a[1], &token, 1) != 1)
      exit();
    close(data_a[0]);
    close(ready[1]);
    close(ack_a[1]);
    exit();
  }

  pid = fork();
  if(pid < 0){
    printf(1, "donation_multi_test: fork reader C failed\n");
    exit();
  }
  if(pid == 0){
    close(data_a[0]);
    close(data_a[1]);
    close(data_c[1]);
    close(ready[0]);
    close(writer_go[0]);
    close(writer_go[1]);
    close(competitor_go[0]);
    close(competitor_go[1]);
    close(ack_a[0]);
    close(ack_a[1]);
    if(setworkflow(3, 200) < 0)
      exit();

    if(read(data_c[0], &prime, 1) != 1)
      exit();
    token = 'c';
    if(write(ready[1], &token, 1) != 1)
      exit();
    if(read(data_c[0], &second, 1) == 0)
      printf(1, "READER_C_RELEASED pid=%d\n", getpid());
    close(data_c[0]);
    close(ready[1]);
    exit();
  }

  pid = fork();
  if(pid < 0){
    printf(1, "donation_multi_test: fork competitor failed\n");
    exit();
  }
  if(pid == 0){
    close(data_a[0]);
    close(data_a[1]);
    close(data_c[0]);
    close(data_c[1]);
    close(ready[0]);
    close(ready[1]);
    close(writer_go[0]);
    close(writer_go[1]);
    close(competitor_go[1]);
    close(ack_a[0]);
    close(ack_a[1]);
    if(setworkflow(4, 250) < 0)
      exit();
    if(read(competitor_go[0], &token, 1) != 1)
      exit();
    printf(1, "COMPETITOR_RUN pid=%d deadline=250\n", getpid());
    close(competitor_go[0]);
    exit();
  }

  close(data_a[0]);
  close(data_a[1]);
  close(data_c[0]);
  close(data_c[1]);
  close(ready[1]);
  close(writer_go[0]);
  close(competitor_go[0]);
  close(ack_a[0]);
  close(ack_a[1]);

  if(read(ready[0], &token, 1) != 1 ||
     read(ready[0], &token, 1) != 1){
    printf(1, "donation_multi_test: reader setup failed\n");
    exit();
  }

  sleep(2);
  token = 'w';
  if(write(writer_go[1], &token, 1) != 1 ||
     write(competitor_go[1], &token, 1) != 1){
    printf(1, "donation_multi_test: release failed\n");
    exit();
  }
  close(ready[0]);
  close(writer_go[1]);
  close(competitor_go[1]);

  for(i = 0; i < 4; i++)
    wait();
  printf(1, "donation_multi_test: complete\n");
  exit();
}
