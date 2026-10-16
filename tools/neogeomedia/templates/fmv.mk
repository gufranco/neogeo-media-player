FMV_ROOT := $(patsubst %/,%,$(dir $(lastword $(MAKEFILE_LIST))))
FMV_SRC = $(FMV_ROOT)/{library_dir}
FMV_MOVIE = $(FMV_ROOT)/{movie_dir}

SRCDIRS += $(FMV_SRC) $(FMV_MOVIE)

FMV_FIRST_BANK ?= 0

FMV_AUDIO ?= {audio}

FMV_STREAM_BANKS = {stream_banks}
FMV_BANK_NUMBERS = {bank_numbers}

FMV_TOTAL_BANKS = $(shell expr $(FMV_FIRST_BANK) + $(FMV_STREAM_BANKS))
FMV_ALL_BANK_NUMBERS = $(shell seq 0 $(shell expr $(FMV_TOTAL_BANKS) - 1))
FMV_PROM2_BYTES = $(shell expr $(FMV_TOTAL_BANKS) \* 1048576)
FMV_CROM_BYTES = {crom_size}
FMV_VROM_BYTES = {vrom_size}
FMV_CROM_DICTIONARY_BYTES = {crom_payload}
FMV_FIRST_FREE_TILE = {tile_count}
FMV_FREE_TILES = {free_tiles}

FMV_CFLAGS = -I$(FMV_SRC) -I$(FMV_MOVIE)
FMV_LDFLAGS = -Wl,--defsym=fmv_stream_base=$(shell expr $(FMV_FIRST_BANK) \* 1048576)

FMV_OBJS = \
	$(BUILDDIR)/$(FMV_SRC)/fmv.o \
	$(BUILDDIR)/$(FMV_SRC)/guard.o \
	$(BUILDDIR)/$(FMV_SRC)/timeline.o \
	$(BUILDDIR)/$(FMV_MOVIE)/movie_data_value.o \
	$(BUILDDIR)/$(FMV_MOVIE)/movie_data.o

ifeq ($(FMV_AUDIO),yes)
FMV_OBJS += $(BUILDDIR)/$(FMV_SRC)/fmv_audio.o

FMV_SOUND_DRIVER = $(BUILDDIR)/$(FMV_SRC)/sound.ihx

$(BUILDDIR)/$(FMV_SRC)/sound.rel: $(FMV_SRC)/sound.s $(FMV_MOVIE)/audio_params.s
	$(Z80SDAS) -g -l -p -u -I$(FMV_MOVIE) -o $@ $<

$(FMV_SOUND_DRIVER): $(BUILDDIR)/$(FMV_SRC)/sound.rel
	$(Z80SDLD) -n -i $@ $<
else
FMV_CFLAGS += -DFMV_NO_AUDIO
endif

FMV_BANK_OBJS = $(foreach bank,$(FMV_BANK_NUMBERS),\
	$(BUILDDIR)/$(FMV_MOVIE)/fmv_stream__bank$(bank).o)

$(BUILDDIR)/$(FMV_MOVIE)/%.o: $(FMV_MOVIE)/%.S
	$(M68KGCC) $(NGCFLAGS) $(CFLAGS) $(FMV_CFLAGS) -c $< -o $@

$(BUILDDIR)/$(FMV_MOVIE)/fmv_stream__bank%.o: $(FMV_MOVIE)/fmv_stream__bank%.S
	$(M68KGCC) $(NGCFLAGS) $(CFLAGS) $(FMV_CFLAGS) -c $< -o $@
	$(M68KOBJCOPY) -R .text -R .data -R .bss $@

ifneq ($(FMV_GAME_OBJS),)
$(foreach bank,$(FMV_BANK_NUMBERS),\
  $(eval $(BUILDDIR)/rom-fmv-bank$(bank).elf: $(FMV_GAME_OBJS) $(FMV_OBJS) \
    $(BUILDDIR)/$(FMV_MOVIE)/fmv_stream__bank$(bank).o)\
  $(eval $(PROM2)_bank$(shell expr $(FMV_FIRST_BANK) + $(bank)): \
    $(BUILDDIR)/rom-fmv-bank$(bank).elf))
$(foreach bank,$(FMV_ALL_BANK_NUMBERS),$(eval $(PROM2): $(PROM2)_bank$(bank)))
endif
