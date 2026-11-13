from xv6_bridge import Xv6Bridge


def main():
    with Xv6Bridge() as bridge:
        output = bridge.run_command("ls")
        print("Files listed inside xv6:")
        print(output)


if __name__ == "__main__":
    main()
