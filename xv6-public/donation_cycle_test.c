#include "types.h"
#include "stat.h"
#include "user.h"

int
main(int argc, char *argv[])
{
  int ab[2], ba[2], ready[2], go_a[2], go_b[2];
  int pid_a, pid_b, waited, i;
  char token, prime;

  if(pipe(ab) < 0 || pipe(ba) < 0 || pipe(ready) < 0 ||
     pipe(go_a) < 0 || pipe(go_b) < 0){
    printf(1, "donation_cycle_test: pipe creation failed\n");
    exit();
  }
  if(setworkflow(3, 250) < 0){
    printf(1, "donation_cycle_test: parent setworkflow failed\n");
    exit();
  }

  pid_a = fork();
  if(pid_a < 0){
    printf(1, "donation_cycle_test: fork A failed\n");
    exit();
  }
  if(pid_a == 0){
    close(ab[0]);
    close(ba[1]);
    close(ready[0]);
    close(go_a[1]);
    close(go_b[0]);
    close(go_b[1]);
    if(setworkflow(1, 100) < 0)
      exit();

    prime = 'a';
    if(write(ab[1], &prime, 1) != 1)
      exit();
    token = 'p';
    if(write(ready[1], &token, 1) != 1)
      exit();
    if(read(ba[0], &prime, 1) != 1)
      exit();
    if(read(go_a[0], &token, 1) != 1)
      exit();

    printf(1, "CYCLE_A_WAIT pid=%d deadline=100\n", getpid());
    token = 'a';
    if(write(ready[1], &token, 1) != 1)
      exit();
    if(read(ba[0], &token, 1) < 0)
      printf(1, "CYCLE_A_KILLED pid=%d\n", getpid());

    close(ab[1]);
    close(ba[0]);
    close(ready[1]);
    close(go_a[0]);
    exit();
  }

  pid_b = fork();
  if(pid_b < 0){
    printf(1, "donation_cycle_test: fork B failed\n");
    exit();
  }
  if(pid_b == 0){
    close(ab[1]);
    close(ba[0]);
    close(ready[0]);
    close(go_b[1]);
    close(go_a[0]);
    close(go_a[1]);
    if(setworkflow(2, 200) < 0)
      exit();

    prime = 'b';
    if(write(ba[1], &prime, 1) != 1)
      exit();
    token = 'p';
    if(write(ready[1], &token, 1) != 1)
      exit();
    if(read(ab[0], &prime, 1) != 1)
      exit();
    if(read(go_b[0], &token, 1) != 1)
      exit();

    printf(1, "CYCLE_B_WAIT pid=%d deadline=200\n", getpid());
    token = 'b';
    if(write(ready[1], &token, 1) != 1)
      exit();
    if(read(ab[0], &token, 1) == 0)
      printf(1, "CYCLE_B_RELEASED pid=%d\n", getpid());

    close(ab[0]);
    close(ba[1]);
    close(ready[1]);
    close(go_b[0]);
    exit();
  }

  close(ab[0]);
  close(ab[1]);
  close(ba[0]);
  close(ba[1]);
  close(ready[1]);
  close(go_a[0]);
  close(go_b[0]);

  for(i = 0; i < 2; i++){
    if(read(ready[0], &token, 1) != 1 || token != 'p'){
      printf(1, "donation_cycle_test: process priming failed\n");
      exit();
    }
  }

  token = 'b';
  if(write(go_b[1], &token, 1) != 1 ||
     read(ready[0], &token, 1) != 1 || token != 'b'){
    printf(1, "donation_cycle_test: could not start B\n");
    exit();
  }

  token = 'a';
  if(write(go_a[1], &token, 1) != 1 ||
     read(ready[0], &token, 1) != 1 || token != 'a'){
    printf(1, "donation_cycle_test: could not start A\n");
    exit();
  }

  printf(1, "CYCLE_ESTABLISHED A=%d B=%d\n", pid_a, pid_b);
  if(kill(pid_a) < 0)
    printf(1, "donation_cycle_test: kill A failed\n");

  close(ready[0]);
  close(go_a[1]);
  close(go_b[1]);
  for(i = 0; i < 2; i++){
    waited = wait();
    if(waited < 0)
      printf(1, "donation_cycle_test: wait failed\n");
  }
  printf(1, "donation_cycle_test: cleanup complete\n");
  exit();
}
