class ProgressBar:
    padding = 5
    fill = "="

    def __init__(self, max: int, title: str) -> None:
        self.title = title
        self.__max = max
        self.__current = 0
        self.update()

    def update(self) -> None:
        if self.__current > self.__max:
            raise ValueError("current value is more than it should be")

        bar_width = len(self.title) + self.padding * 2

        perc = self.__current / self.__max
        units = round(bar_width * perc)

        if not hasattr(self, "_bar_content"):
            self._bar_content = [" "] * self.padding + list(self.title) + [" "] * self.padding

        for i in range(units):
            c = self._bar_content[i]
            self._bar_content[i] = f"\033[2m{self.fill}\033[0m" if c == " " else c

        print(f"\r[{''.join(self._bar_content)}] {perc:.2%}", end="")

        if self.__current == self.__max:
            print()

        else:
            self.__current += 1
